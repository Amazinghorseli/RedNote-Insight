"""
graph.py - LangGraph 图编排
将 supervisor + agents 组合为可执行的 LangGraph 应用
融合原 step07 自纠错 + step08 Multi-Agent
"""
from typing import TypedDict, List, Literal
from langgraph.graph import StateGraph, START, END
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.config import LLM_CONFIG, RETRY_LIMIT, RERANKER_THRESHOLD
from src.retrievers import APIReranker
from src.logger import logger


# ===== State =====
class AgentState(TypedDict):
    question: str                     # 用户问题
    rewritten_question: str           # 重写后的问题
    strategy: str                     # Supervisor 选的策略
    documents: List[Document]         # 检索到的原始文档
    relevant_docs: List[Document]     # 评估后保留的文档
    generation: str                   # 最终回答
    retry_count: int                  # 已重试次数


# ===== 初始化 =====
llm = ChatOpenAI(**LLM_CONFIG)


# ===== 生成 Prompt =====
gen_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是知识问答助手。基于上下文用中文回答问题。\n"
     "规则：有答案就准确回答；没答案就说无法回答；不要编造。\n\n"
     "上下文：\n{context}"),
    ("human", "{question}"),
])


# ===== 图节点工厂 =====
def create_retrieve_node(vectorstore, bm25_retriever, hybrid_retriever):
    """创建检索节点 - 由 Supervisor 选中的策略执行"""
    K = 5  # 检索数量
    agents = {
        "vector": lambda q: vectorstore.similarity_search(q, k=K),
        "keyword": lambda q: bm25_retriever(q, k=K),
        "hybrid": lambda q: hybrid_retriever.hybrid_search(q),
    }

    def retrieve_node(state: AgentState) -> dict:
        query = state.get("rewritten_question") or state["question"]
        strategy = state.get("strategy", "hybrid")
        agent = agents.get(strategy, agents["hybrid"])
        logger.info(f"策略={strategy} | 查询={query[:60]}")
        docs = agent(query)
        logger.info(f"检索到 {len(docs)} 篇文档")
        return {"documents": docs}

    return retrieve_node


def create_supervisor_node():
    """创建 Supervisor 节点 - 选择策略"""
    from src.agents.supervisor import Supervisor

    supervisor = Supervisor()

    def supervisor_node(state: AgentState) -> dict:
        strategy = supervisor.decide(state["question"], ["vector", "keyword", "hybrid"])
        return {"strategy": strategy}

    return supervisor_node


# ===== 固定节点 =====
def create_rerank_node(reranker: APIReranker):
    """创建重排序节点 — 用 CrossEncoder 替代 LLM 做相关性评估"""
    def rerank_node(state: AgentState) -> dict:
        docs = state.get("documents", [])
        if not docs:
            return {"relevant_docs": []}

        query = state.get("rewritten_question") or state["question"]
        logger.info(f"CrossEncoder 评估 {len(docs)} 篇文档...")

        # API 调用
        scores = reranker.rerank(query, docs)

        # 按阈值过滤
        relevant = [
            doc for doc, score in zip(docs, scores)
            if score >= RERANKER_THRESHOLD
        ]

        # 按分数降序排列
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


def rewrite_node(state: AgentState) -> dict:
    """重写查询，提高检索质量"""
    rewrite_prompt = ChatPromptTemplate.from_messages([
        ("system", "你是查询重写专家。根据原问题重写更精确的检索查询。"
         "只输出重写后的查询，不要解释。"),
        ("human", "原问题：{question}"),
    ])
    logger.info("优化查询重写...")
    msg = rewrite_prompt.format_messages(question=state["question"])
    rewritten = llm.invoke(msg).content.strip()
    count = state["retry_count"] + 1
    logger.info(f"第 {count} 次重写: '{rewritten[:80]}'")
    return {"rewritten_question": rewritten, "retry_count": count}


def generate_node(state: AgentState) -> dict:
    """基于相关文档生成回答"""
    logger.info("正在生成回答...")
    docs = state.get("relevant_docs") or state.get("documents", [])
    context = "\n---\n".join(
        f"[文档{i+1}] {d.page_content}" for i, d in enumerate(docs)
    )
    msg = gen_prompt.format_messages(context=context, question=state["question"])
    response = llm.invoke(msg)
    return {"generation": response.content}


def fallback_node(state: AgentState) -> dict:
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
def build_graph(vectorstore, bm25_retriever, hybrid_retriever, reranker=None):
    """
    构建完整的 LangGraph：
    START -> supervisor -> retrieve -> grade
      ├─ generate ──→ END
      ├─ rewrite ──→ retrieve (循环)
      └─ fallback ──→ END

    reranker: APIReranker 实例（CrossEncoder API），为 None 时自动创建
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
