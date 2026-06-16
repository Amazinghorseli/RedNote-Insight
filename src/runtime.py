"""
runtime.py — 运行时状态管理
============================
统一管理向量库、BM25 索引、HybridRetriever、LangGraph 的
初始化与增量更新，消除 app.py / api.py 之间的重复代码。
"""
from dataclasses import dataclass, field
from typing import Callable, Optional
from langchain_core.documents import Document

from src.logger import logger


@dataclass
class Runtime:
    """运行时状态容器"""
    vectorstore: any = None
    chunks: list[Document] = field(default_factory=list)
    bm25: any = None
    hybrid_retriever: any = None
    bm25_search: Callable = None
    graph: any = None
    reranker: any = None
    raw_dir: str = ""
    chroma_dir: str = ""

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)


def init_runtime(raw_dir: str, chroma_dir: str, reranker=None) -> Runtime:
    """
    冷启动：加载向量库 → 构建全部索引 → 返回 Runtime。
    首次调用或页面刷新时使用。
    """
    from src.ingestion import load_raw_documents, chunk_documents, load_vectorstore, build_vectorstore
    from src.retrievers import HybridRetriever, APIReranker

    # 检查是否存在已构建的向量库
    import os
    chroma_db_file = os.path.join(chroma_dir, "chroma.sqlite3")

    if os.path.exists(chroma_db_file):
        logger.info("加载已有向量库...")
        vectorstore = load_vectorstore()
    else:
        logger.info("首次运行，构建向量库...")
        docs = load_raw_documents()
        chunks = chunk_documents(docs)
        vectorstore = build_vectorstore(chunks)

    if reranker is None:
        reranker = APIReranker()

    runtime = Runtime(vectorstore=vectorstore, reranker=reranker,
                      raw_dir=raw_dir, chroma_dir=chroma_dir)
    _rebuild_all_indexes(runtime)
    return runtime


def incremental_update(runtime: Runtime) -> Runtime:
    """
    增量更新：数据文件变化后调用。
    执行 增量入库 → 重建 BM25/Hybrid/Graph。
    返回更新后的 runtime（原地修改）。
    """
    from src.ingestion import incremental_ingest
    incremental_ingest(runtime.raw_dir, runtime.vectorstore)
    return _rebuild_all_indexes(runtime)


def _rebuild_all_indexes(runtime: Runtime) -> Runtime:
    """内部：从磁盘重建所有索引"""
    from src.ingestion import rebuild_all_chunks
    from src.retrievers import HybridRetriever
    from src.graph import build_graph
    from rank_bm25 import BM25Okapi
    import jieba

    logger.info("重建全量索引...")
    chunks = rebuild_all_chunks(runtime.raw_dir)

    # BM25
    tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
    bm25 = BM25Okapi(tokenized)

    # HybridRetriever（替换旧引用）
    hybrid_retriever = HybridRetriever(runtime.vectorstore, chunks)

    # BM25 搜索闭包
    def bm25_search(query: str, k: int = 3):
        tokenized_query = list(jieba.cut(query))
        scores = bm25.get_scores(tokenized_query)
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [chunks[i] for i in top_idx]

    # LangGraph
    graph = build_graph(runtime.vectorstore, bm25_search, hybrid_retriever,
                        reranker=runtime.reranker)

    runtime.chunks = chunks
    runtime.bm25 = bm25
    runtime.hybrid_retriever = hybrid_retriever
    runtime.bm25_search = bm25_search
    runtime.graph = graph

    logger.info(f"索引重建完成，chunks={len(chunks)}")
    return runtime
