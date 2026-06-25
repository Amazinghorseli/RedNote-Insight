"""
graph.py — LangGraph 图编排（全异步）
======================================
将 supervisor + agents 组合为可执行的 LangGraph 应用。
所有节点均为 async，由 build_async_graph 构建。
Prompt 从 YAML 加载（src/prompts/）。

用法:
    graph = build_async_graph(vectorstore, bm25_search, hybrid_retriever, reranker)
    result = await graph.ainvoke({"question": "..."})
"""
import asyncio
from typing import TypedDict, List, Literal
from langgraph.graph import StateGraph, START, END
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.config import LLM_CONFIG, RETRY_LIMIT, RERANKER_THRESHOLD
from src.retrievers import APIReranker
from src.logger import logger
from src.core.prompt_loader import get_prompt_loader
from src.core.query_utils import clean_query, is_brand_comparison, resolve_k


# ===== State =====
class AgentState(TypedDict):
    question: str
    rewritten_question: str
    strategy: str
    documents: List[Document]
    relevant_docs: List[Document]
    generation: str
    retry_count: int


# ===== 初始化 =====
llm = ChatOpenAI(**LLM_CONFIG)
prompt_loader = get_prompt_loader()


# ===== 图节点工厂（异步） =====
def create_retrieve_node(vectorstore, bm25_retriever, hybrid_retriever):
    """创建检索节点 — 由 Supervisor 选中的策略执行（异步）

    内置查询清洗 + 品牌/对比问题动态扩大检索范围。
    """
    BASE_K = 5
    BRAND_K = 8

    async def retrieve_node(state: AgentState) -> dict:
        query = state.get("rewritten_question") or state["question"]
        # 查询清洗：去除纯数字噪音
        original = query
        query = clean_query(query)
        if query != original:
            logger.info(f"查询清洗: '{original[:60]}' -> '{query[:60]}'")

        strategy = state.get("strategy", "hybrid")
        # 品牌/对比问题：扩大检索范围
        k = resolve_k(query, BASE_K, BRAND_K)
        logger.info(f"策略={strategy} | K={k} | 查询={query[:60]}")

        loop = asyncio.get_running_loop()

        if strategy == "hybrid":
            docs = await hybrid_retriever.ahybrid_search(query, k=k, bm25_k=max(40, k*5), final_k=k)
        elif strategy == "vector":
            # 兼容 PG (async) 和 ChromaDB (sync) 向量存储
            if hasattr(vectorstore, 'similarity_search'):
                import inspect
                if inspect.iscoroutinefunction(vectorstore.similarity_search):
                    docs = await vectorstore.similarity_search(query, k=k)
                else:
                    docs = await loop.run_in_executor(
                        None, lambda: vectorstore.similarity_search(query, k=k)
                    )
            else:
                docs = []
        else:
            docs = await loop.run_in_executor(
                None, lambda: bm25_retriever(query, k=k)
            )

        logger.info(f"检索到 {len(docs)} 篇文档")
        return {"documents": docs}

    return retrieve_node


def create_supervisor_node():
    """创建 Supervisor 节点 — 异步选择策略"""
    from src.agents.supervisor import Supervisor
    supervisor = Supervisor()

    async def supervisor_node(state: AgentState) -> dict:
        strategy = await supervisor.adecide(state["question"], ["vector", "keyword", "hybrid"])
        return {"strategy": strategy}

    return supervisor_node


def create_rerank_node(reranker: APIReranker):
    """创建重排序节点 — 异步 CrossEncoder 评估"""
    async def rerank_node(state: AgentState) -> dict:
        docs = state.get("documents", [])
        if not docs:
            return {"relevant_docs": []}

        query = state.get("rewritten_question") or state["question"]
        logger.info(f"CrossEncoder 评估 {len(docs)} 篇文档...")

        scores = await reranker.arerank(query, docs)
        scored = sorted(
            [(doc, score) for doc, score in zip(docs, scores) if score >= RERANKER_THRESHOLD],
            key=lambda x: x[1],
            reverse=True,
        )
        relevant = [doc for doc, _ in scored]

        logger.info(f"相关 {len(relevant)} / 共 {len(docs)} 篇 (threshold={RERANKER_THRESHOLD})")
        for doc, score in scored[:3]:
            src = doc.metadata.get("source", "?")[:35]
            logger.debug(f"评分 {score:.4f} | {src}")
        return {"relevant_docs": relevant}

    return rerank_node


async def rewrite_node(state: AgentState) -> dict:
    """重写查询，提高检索质量（异步）"""
    logger.info("优化查询重写...")
    rewrite_prompt = prompt_loader.load("rewrite_query", "v2")
    msg = rewrite_prompt.format_messages(question=state["question"])
    response = await llm.ainvoke(msg)
    rewritten = response.content.strip()
    count = state["retry_count"] + 1
    logger.info(f"第 {count} 次重写: '{rewritten[:80]}'")
    return {"rewritten_question": rewritten, "retry_count": count}


async def generate_node(state: AgentState) -> dict:
    """基于相关文档生成回答（异步）"""
    logger.info("正在生成回答...")
    docs = state.get("relevant_docs") or state.get("documents", [])
    context = "\n---\n".join(
        f"[文档{i+1}] {d.page_content}" for i, d in enumerate(docs)
    )
    gen_prompt = prompt_loader.load("gen_answer", "v2")
    msg = gen_prompt.format_messages(context=context, question=state["question"])
    response = await llm.ainvoke(msg)
    return {"generation": response.content}


async def fallback_node(state: AgentState) -> dict:
    """兜底：无法回答"""
    logger.warning("无法找到相关信息，触发 fallback")
    return {"generation": "抱歉，根据现有资料无法回答这个问题。"}


# ===== 条件路由 =====
def decide_route(state: AgentState) -> Literal["generate", "rewrite", "fallback"]:
    if state.get("relevant_docs"):
        return "generate"
    elif state["retry_count"] < RETRY_LIMIT:
        return "rewrite"
    else:
        return "fallback"


# ===== 构图 =====
def build_async_graph(vectorstore, bm25_retriever, hybrid_retriever, reranker=None):
    """
    构建全异步 LangGraph，通过 graph.ainvoke() 调用。

    Args:
        vectorstore: Chroma 向量库
        bm25_retriever: BM25 检索函数
        hybrid_retriever: HybridRetriever 实例
        reranker: APIReranker 实例
    """
    if reranker is None:
        reranker = APIReranker()

    builder = StateGraph(AgentState)

    builder.add_node("supervisor", create_supervisor_node())
    builder.add_node("retrieve", create_retrieve_node(vectorstore, bm25_retriever, hybrid_retriever))
    builder.add_node("grade", create_rerank_node(reranker))
    builder.add_node("rewrite", rewrite_node)
    builder.add_node("generate", generate_node)
    builder.add_node("fallback", fallback_node)

    builder.add_edge(START, "supervisor")
    builder.add_edge("supervisor", "retrieve")
    builder.add_edge("retrieve", "grade")
    builder.add_conditional_edges(
        "grade",
        decide_route,
        {
            "generate": "generate",
            "rewrite": "rewrite",
            "fallback": "fallback",
        },
    )
    builder.add_edge("rewrite", "retrieve")
    builder.add_edge("generate", END)
    builder.add_edge("fallback", END)

    return builder.compile()
