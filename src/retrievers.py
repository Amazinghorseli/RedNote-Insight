"""
retrievers.py - 混合检索 + 重排序
合并自原 step03_hybrid_retriever + step04_reranker
"""
from src.logger import logger
from typing import List
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


class Reranker:
    """使用 CrossEncoder 对检索结果重排序（本地模式，需安装 sentence-transformers）"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            raise ImportError(
                "本地 Reranker 需要 sentence-transformers。"
                "请运行: pip install sentence-transformers\n"
                "或使用 APIReranker（基于 API，无需本地模型）"
            )
        logger.info(f"[Reranker] 加载模型: {model_name}")
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, documents: list[Document], top_k: int = 3) -> list[Document]:
        if not documents:
            return []
        pairs = [(query, doc.page_content) for doc in documents]
        scores = self.model.predict(pairs, show_progress_bar=False)
        scored = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
        reranked = [doc for doc, _ in scored[:top_k]]
        logger.info(f"[Reranker] {len(documents)} -> {len(reranked)} 篇")
        return reranked
