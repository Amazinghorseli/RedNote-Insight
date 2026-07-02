"""
retrievers.py - 混合检索 + 重排序
合并自原 step03_hybrid_retriever + step04_reranker
支持 ChromaDB（默认）和 PostgreSQL + pgvector（可选）双模式
"""
import asyncio

from src.logger import logger
from typing import List, Optional
from rank_bm25 import BM25Okapi
from langchain_core.documents import Document
import jieba


class HybridRetriever:
    """混合检索：向量检索 + BM25 关键词检索 + RRF 融合"""

    def __init__(self, vectorstore, chunks: list[Document]):
        self.vectorstore = vectorstore
        self.chunks = chunks
        self.bm25 = self._build_bm25(chunks)

    def _build_bm25(self, chunks: list[Document]) -> BM25Okapi:
        logger.info("[BM25] 构建索引...")
        tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
        logger.info(f"BM25 索引完成，共 {len(tokenized)} 篇文档")
        return BM25Okapi(tokenized)

    def hybrid_search(
        self,
        query: str,
        k: int = 10,
        bm25_k: int = 25,
        final_k: int = 10,
    ) -> list[Document]:
        """RRF（Reciprocal Rank Fusion）融合检索"""
        # 1. 向量检索
        vector_results = self.vectorstore.similarity_search_with_score(query, k=k)
        logger.info(f"[VECTOR] 向量检索: {len(vector_results)} 个结果")

        # 2. BM25 检索
        tokenized_query = list(jieba.cut(query))
        bm25_scores = self.bm25.get_scores(tokenized_query)
        bm25_indices = sorted(
            range(len(bm25_scores)),
            key=lambda i: bm25_scores[i],
            reverse=True,
        )[:bm25_k]
        logger.info(f"[BM25] BM25 检索: {len(bm25_indices)} 个结果")

        # 3. RRF 融合
        rrf_scores = {}
        for rank, (doc, _) in enumerate(vector_results):
            doc_id = doc.metadata.get("source", "") + doc.page_content[:50]
            rrf_scores[doc_id] = 1.0 / (60 + rank + 1)
        for rank, idx in enumerate(bm25_indices):
            doc = self.chunks[idx]
            doc_id = doc.metadata.get("source", "") + doc.page_content[:50]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (60 + rank + 1)

        # 4. 排序取 Top-K
        ranked_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)[:final_k]

        # 5. 映射回 Document
        doc_map = {}
        for doc, _ in vector_results:
            doc_map[doc.metadata.get("source", "") + doc.page_content[:50]] = doc
        for doc in self.chunks:
            doc_map[doc.metadata.get("source", "") + doc.page_content[:50]] = doc

        return [doc_map[rid] for rid in ranked_ids]

    async def ahybrid_search(
        self,
        query: str,
        k: int = 10,
        bm25_k: int = 25,
        final_k: int = 10,
    ) -> list[Document]:
        """异步版本：RRF 融合检索（FastAPI async 端点使用）

        向量检索和 BM25 检索并行执行，不阻塞事件循环。
        ChromaDB 目前无原生 async，用 run_in_executor 放到线程池。
        """
        loop = asyncio.get_running_loop()

        # 向量检索 → 线程池
        vector_results = await loop.run_in_executor(
            None, lambda: self.vectorstore.similarity_search_with_score(query, k=k)
        )

        # BM25 检索 → 线程池
        def bm25_work():
            tokenized_query = list(jieba.cut(query))
            bm25_scores = self.bm25.get_scores(tokenized_query)
            return sorted(
                range(len(bm25_scores)),
                key=lambda i: bm25_scores[i],
                reverse=True,
            )[:bm25_k]

        bm25_indices = await loop.run_in_executor(None, bm25_work)

        # RRF 融合（纯 CPU，很快，不异步）
        rrf_scores = {}
        for rank, (doc, _) in enumerate(vector_results):
            doc_id = doc.metadata.get("source", "") + doc.page_content[:50]
            rrf_scores[doc_id] = 1.0 / (60 + rank + 1)
        for rank, idx in enumerate(bm25_indices):
            doc = self.chunks[idx]
            doc_id = doc.metadata.get("source", "") + doc.page_content[:50]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (60 + rank + 1)

        ranked_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)[:final_k]

        doc_map = {}
        for doc, _ in vector_results:
            doc_map[doc.metadata.get("source", "") + doc.page_content[:50]] = doc
        for doc in self.chunks:
            doc_map[doc.metadata.get("source", "") + doc.page_content[:50]] = doc

        return [doc_map[rid] for rid in ranked_ids]


class APIReranker:
    """CrossEncoder 重排序器（通过 SiliconFlow API）

    用专门的 reranker 模型对 query-doc 对做相关性打分，
    比 LLM-as-Judge 更准、更快、更便宜。
    """

    def __init__(self, model: str = None, api_key: str = None, base_url: str = None):
        from src.config import RERANKER_CONFIG
        cfg = RERANKER_CONFIG
        self.model = model or cfg["model"]
        self.api_key = api_key or cfg["api_key"]
        self.base_url = (base_url or cfg["base_url"]).rstrip("/")

    def rerank(self, query: str, documents: list[Document]) -> list[float]:
        """对 query 和每篇 doc 做相关性打分，返回分数列表（与 documents 顺序一致）"""
        import requests

        contents = [d.page_content[:1000] for d in documents]
        payload = {
            "model": self.model,
            "query": query,
            "documents": contents,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        resp = requests.post(
            f"{self.base_url}/rerank", headers=headers, json=payload, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        # 将结果映射回原始顺序
        scores = [0.0] * len(documents)
        for result in data.get("results", []):
            scores[result["index"]] = result["relevance_score"]

        return scores

    async def arerank(self, query: str, documents: list[Document]) -> list[float]:
        """异步版本：对 query 和每篇 doc 做相关性打分（httpx 替代 requests）

        FastAPI async 端点使用，避免阻塞事件循环。
        同步版本 rerank() 保留以兼容 Streamlit 等场景。
        """
        import httpx

        contents = [d.page_content[:1000] for d in documents]
        payload = {
            "model": self.model,
            "query": query,
            "documents": contents,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/rerank", headers=headers, json=payload
            )
            resp.raise_for_status()
            data = resp.json()

        scores = [0.0] * len(documents)
        for result in data.get("results", []):
            scores[result["index"]] = result["relevance_score"]

        return scores


# ================================================================
# PostgreSQL + pgvector 向量检索
# ================================================================

class PGVectorStore:
    """PostgreSQL + pgvector 向量存储适配器

    提供与 ChromaDB 兼容的接口（similarity_search 等），
    方便无缝切换。

    用法:
        pg = PGVectorStore()
        docs = await pg.similarity_search("磁吸感应灯", k=5)
    """

    def __init__(self, embedding_model=None):
        if embedding_model is None:
            from src.ingestion import get_embeddings
            self.embedding_model = get_embeddings()
        else:
            self.embedding_model = embedding_model

    async def similarity_search(
        self, query: str, k: int = 5
    ) -> list[Document]:
        """向量相似度搜索（返回 Document 对象）"""
        from src.core.database import get_db, search_by_vector

        # 1. Embed 查询
        import asyncio as _asyncio
        loop = _asyncio.get_running_loop()
        query_embedding = await loop.run_in_executor(
            None, lambda: self.embedding_model.embed_query(query)
        )

        # 2. 搜索
        results = []
        async for session in get_db():
            rows = await search_by_vector(session, query_embedding, k=k)

        # 3. 转为 Document 对象
        for row in rows:
            doc = Document(
                page_content=row["content"],
                metadata=row.get("metadata", {}),
            )
            results.append(doc)

        return results

    async def similarity_search_with_score(
        self, query: str, k: int = 5
    ) -> list[tuple[Document, float]]:
        """向量相似度搜索（带分数）"""
        from src.core.database import get_db, search_by_vector

        import asyncio as _asyncio
        loop = _asyncio.get_running_loop()
        query_embedding = await loop.run_in_executor(
            None, lambda: self.embedding_model.embed_query(query)
        )

        results = []
        async for session in get_db():
            rows = await search_by_vector(session, query_embedding, k=k)

        for row in rows:
            doc = Document(
                page_content=row["content"],
                metadata=row.get("metadata", {}),
            )
            results.append((doc, row["score"]))

        return results

    async def count(self) -> int:
        """获取文档总数"""
        from src.core.database import get_db, get_document_count
        async for session in get_db():
            return await get_document_count(session)
        return 0


class PgHybridRetriever:
    """基于 PG 的混合检索器（向量 + BM25 + RRF 融合）

    用法:
        retriever = PgHybridRetriever(pg_vectorstore, chunks)
        docs = await retriever.ahybrid_search("磁吸感应灯")
    """

    def __init__(self, pg_vectorstore: PGVectorStore, chunks: list[Document]):
        self.pg = pg_vectorstore
        self.chunks = chunks
        self.bm25 = self._build_bm25(chunks)

    def _build_bm25(self, chunks: list[Document]) -> BM25Okapi:
        logger.info("[PG-BM25] 构建索引...")
        tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
        logger.info(f"PG-BM25 索引完成，共 {len(tokenized)} 篇文档")
        return BM25Okapi(tokenized)

    async def ahybrid_search(
        self,
        query: str,
        k: int = 10,
        bm25_k: int = 25,
        final_k: int = 10,
    ) -> list[Document]:
        """异步 RRF 融合检索（PG 版）"""
        loop = asyncio.get_running_loop()

        # 1. PG 向量检索
        vector_results = await self.pg.similarity_search_with_score(query, k=k)
        logger.info(f"[PG-VECTOR] 向量检索: {len(vector_results)} 个结果")

        # 2. BM25 检索
        def bm25_work():
            tokenized_query = list(jieba.cut(query))
            bm25_scores = self.bm25.get_scores(tokenized_query)
            return sorted(
                range(len(bm25_scores)),
                key=lambda i: bm25_scores[i],
                reverse=True,
            )[:bm25_k]

        bm25_indices = await loop.run_in_executor(None, bm25_work)
        logger.info(f"[PG-BM25] BM25 检索: {len(bm25_indices)} 个结果")

        # 3. RRF 融合
        rrf_scores = {}
        for rank, (doc, _) in enumerate(vector_results):
            doc_id = doc.metadata.get("source", "") + doc.page_content[:50]
            rrf_scores[doc_id] = 1.0 / (60 + rank + 1)
        for rank, idx in enumerate(bm25_indices):
            doc = self.chunks[idx]
            doc_id = doc.metadata.get("source", "") + doc.page_content[:50]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (60 + rank + 1)

        ranked_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)[:final_k]

        # 4. 映射回 Document
        doc_map = {}
        for doc, _ in vector_results:
            doc_map[doc.metadata.get("source", "") + doc.page_content[:50]] = doc
        for doc in self.chunks:
            doc_map[doc.metadata.get("source", "") + doc.page_content[:50]] = doc

        return [doc_map[rid] for rid in ranked_ids if rid in doc_map]


async def create_pg_vectorstore() -> Optional[PGVectorStore]:
    """尝试创建 PG 向量存储（如果 PG 可用）

    返回 None 表示 PG 不可用，应回退到 ChromaDB。
    """
    try:
        from src.core.database import init_db, get_db, get_document_count

        await init_db()

        async for session in get_db():
            count = await get_document_count(session)
            if count > 0:
                logger.info(f"pg_vectorstore_ready: {count} documents")
                return PGVectorStore()
            else:
                logger.info("pg_vectorstore_empty: no documents, using ChromaDB fallback")
                return None

    except Exception as e:
        logger.warning(f"pg_unavailable: {e}, falling back to ChromaDB")
        return None
