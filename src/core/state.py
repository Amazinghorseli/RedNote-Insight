"""
state.py — 生产级 AppState 容器
==================================
替换全局 _runtime dict，提供：
- asyncio.Lock 保证线程安全
- lifespan 中冷启动初始化
- 增量重建索引
- 自动切换 ChromaDB / PostgreSQL+pgvector

用法:
    from src.core.state import AppState, init_app_state

    state = AppState()
    await state.initialize()
    await state.rebuild_indexes()
"""
import os
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Callable

from src.config import settings
from src.logger import logger


@dataclass
class AppState:
    """生产级运行时状态容器，替代全局 _runtime dict

    所有可变操作受 asyncio.Lock 保护，线程安全。
    """

    # --- 组件 ---
    vectorstore: any = None
    chunks: list = field(default_factory=list)
    bm25: any = None
    hybrid_retriever: any = None
    bm25_search: Optional[Callable] = None
    graph: any = None
    reranker: any = None

    # --- 路径 ---
    raw_dir: str = ""
    chroma_dir: str = ""

    # --- 生命周期 ---
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _initialized: bool = False
    _error: Optional[str] = None
    _use_pg: bool = False  # True=PG+pgvector, False=ChromaDB

    # --- 统计 ---
    stats: dict = field(default_factory=lambda: {
        "categories": [],
        "total_notes": 0,
        "total_chunks": 0,
    })

    @property
    def is_ready(self) -> bool:
        return self._initialized and not self._error

    @property
    def error(self) -> Optional[str]:
        return self._error

    async def initialize(self) -> None:
        """冷启动初始化（线程安全，可重入）"""
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            try:
                await self._do_initialize()
                self._initialized = True
                logger.info(f"AppState READY — {self.stats['total_chunks']} chunks")
            except Exception as e:
                self._error = str(e)
                logger.error(f"AppState init failed: {e}")

    async def rebuild_indexes(self) -> None:
        """增量入库 + 重建 BM25/Hybrid/Graph 索引"""
        async with self._lock:
            from src.ingestion import incremental_ingest, rebuild_all_chunks
            from src.retrievers import HybridRetriever, PgHybridRetriever
            from src.graph import build_async_graph
            from rank_bm25 import BM25Okapi
            import jieba

            logger.info("[AppState] 重建全量索引...")

            if self._use_pg:
                # PG 增量入库
                from src.ingestion import incremental_ingest_to_pg
                await incremental_ingest_to_pg(self.raw_dir)
            else:
                # ChromaDB 增量入库
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, incremental_ingest, self.raw_dir, self.vectorstore)

            chunks = rebuild_all_chunks(self.raw_dir)
            tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
            bm25 = BM25Okapi(tokenized)

            if self._use_pg:
                hr = PgHybridRetriever(self.vectorstore, chunks)
            else:
                hr = HybridRetriever(self.vectorstore, chunks)

            def bms(q, k=3):
                scores = bm25.get_scores(list(jieba.cut(q)))
                return [chunks[i] for i in sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]]

            self.chunks = chunks
            self.bm25 = bm25
            self.hybrid_retriever = hr
            self.bm25_search = bms
            self.graph = build_async_graph(self.vectorstore, bms, hr, reranker=self.reranker)
            self._refresh_stats()
            logger.info(f"[AppState] 索引重建完成 — {len(chunks)} chunks (pg={self._use_pg})")

    async def _do_initialize(self) -> None:
        """实际初始化逻辑：优先 PG，回退 ChromaDB"""
        from src.ingestion import rebuild_all_chunks, load_vectorstore
        from src.retrievers import HybridRetriever, APIReranker, create_pg_vectorstore, PgHybridRetriever
        from src.graph import build_async_graph
        from rank_bm25 import BM25Okapi
        import jieba

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.raw_dir = os.path.join(project_root, "data", "raw")
        self.chroma_dir = os.path.join(project_root, "data", "chroma_db")

        loop = asyncio.get_running_loop()

        raw_files = [f for f in os.listdir(self.raw_dir) if f.endswith((".txt", ".md"))] \
            if os.path.exists(self.raw_dir) else []
        if not raw_files:
            self._error = "暂无数据，请用 generate_data.py 生成数据后刷新"
            return

        self.reranker = APIReranker()
        chunks = rebuild_all_chunks(self.raw_dir)

        # ===== 优先尝试 PostgreSQL + pgvector =====
        vectorstore = None
        if settings.database_url:
            logger.info("trying_pg_vectorstore...")
            try:
                pg_store = await create_pg_vectorstore()
                if pg_store is not None:
                    vectorstore = pg_store  # PGVectorStore
                    self._use_pg = True
                    logger.info("using_pg_vectorstore")
                else:
                    # PG 可用但为空，写入数据
                    logger.info("pg_empty, ingesting...")
                    from src.ingestion import ingest_to_pg
                    await ingest_to_pg(self.raw_dir)
                    pg_store = await create_pg_vectorstore()
                    if pg_store:
                        vectorstore = pg_store
                        self._use_pg = True
                        logger.info("pg_ingested_and_ready")
            except Exception as e:
                logger.warning(f"pg_init_failed: {e}, falling back to ChromaDB")
                self._use_pg = False

        # ===== 回退 ChromaDB =====
        if vectorstore is None:
            self._use_pg = False
            chroma_db_file = os.path.join(self.chroma_dir, "chroma.sqlite3")
            if os.path.exists(chroma_db_file):
                vectorstore = await loop.run_in_executor(None, load_vectorstore)
            else:
                from src.ingestion import load_raw_documents, chunk_documents, build_vectorstore
                docs = load_raw_documents()
                chunks_for_build = chunk_documents(docs)
                vectorstore = await loop.run_in_executor(None, lambda: build_vectorstore(chunks_for_build))
            logger.info("using_chromadb_vectorstore")

        # ===== 构建 BM25 + Hybrid + Graph =====
        tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
        bm25 = BM25Okapi(tokenized)

        if self._use_pg:
            hr = PgHybridRetriever(vectorstore, chunks)  # PG 版
        else:
            hr = HybridRetriever(vectorstore, chunks)     # ChromaDB 版

        def bm25_search(query: str, k: int = 3):
            tokenized_query = list(jieba.cut(query))
            scores = bm25.get_scores(tokenized_query)
            top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
            return [chunks[i] for i in top_idx]

        self.vectorstore = vectorstore
        self.chunks = chunks
        self.bm25 = bm25
        self.hybrid_retriever = hr
        self.bm25_search = bm25_search
        self.graph = build_async_graph(vectorstore, bm25_search, hr, reranker=self.reranker)
        self._refresh_stats()

    def _refresh_stats(self) -> None:
        categories = list(set(d.metadata.get("category", "未分类") for d in self.chunks))
        raw_files = [f for f in os.listdir(self.raw_dir) if f.endswith((".txt", ".md"))] \
            if os.path.exists(self.raw_dir) else []
        self.stats = {
            "categories": categories,
            "total_notes": len(raw_files),
            "total_chunks": len(self.chunks),
        }

    # ================================================================
    # 同步方法（供 Streamlit 等同步框架使用）
    # ================================================================

    def init_sync(self) -> None:
        """同步初始化（供 Streamlit 使用）

        Streamlit 不支持 async，但 AppState.initialize() 是 async 的。
        通过新建事件循环桥接。
        """
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self.initialize())
        finally:
            loop.close()

    def rebuild_sync(self) -> None:
        """同步重建索引（供 Streamlit 使用）"""
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self.rebuild_indexes())
        finally:
            loop.close()


async def init_app_state() -> AppState:
    """创建并初始化 AppState（供 lifespan 使用）"""
    state = AppState()
    await state.initialize()
    return state

