"""
rag_pipeline.py - 基础 RAG 问答管道
源自原 step05_rag_chain.py
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document

from src.config import LLM_CONFIG


class BasicRAG:
    """基础 RAG：检索 → 生成"""

    def __init__(self, retriever, reranker=None, llm=None):
        self.retriever = retriever
        self.reranker = reranker
        self.llm = llm or ChatOpenAI(**LLM_CONFIG)

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "你是知识问答助手。基于上下文用中文回答问题。\n"
             "规则：有答案就准确回答；没答案就说无法回答；不要编造。\n\n"
             "上下文：\n{context}"),
            ("human", "{question}"),
        ])

    def _format_context(self, docs: list[Document]) -> str:
        parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "未知来源")
            parts.append(f"[文档{i}] (来自: {source})\n{doc.page_content}")
        return "\n---\n".join(parts)

    def query(self, question: str) -> tuple[str, list[Document]]:
        """执行一次 RAG 查询"""
        docs = self.retriever.hybrid_search(question, k=10, final_k=10)
        if self.reranker:
            docs = self.reranker.rerank(question, docs, top_k=3)

        context = self._format_context(docs)
        messages = self.prompt.format_messages(context=context, question=question)
        response = self.llm.invoke(messages)

        return response.content, docs
