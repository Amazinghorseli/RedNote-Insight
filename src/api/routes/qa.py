"""qa.py — QA 问答端点（快速通道）"""
import time
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
import jieba

from src.api.dependencies import get_app_state
from src.core.state import AppState
from src.config import LLM_CONFIG
from src.core.prompt_loader import get_prompt_loader

router = APIRouter(tags=["qa"])


class QARequest(BaseModel):
    question: str
    strategy: str = "hybrid"


class QAResponse(BaseModel):
    success: bool
    question: str
    answer: str
    elapsed: float


from src.core.query_utils import clean_query, is_brand_comparison

_NO_DATA = "知识库中暂无该品类的数据。请换一个品类试试，或通过选品洞察触发实时抓取。"
_QUESTION_STOP = {"哪个", "哪款", "哪家", "品牌", "推荐", "好", "什么", "怎么", "如何", "多少", "对比", "测评", "排行", "有没有", "值得", "建议", "选择", "区别"}

def _any_relevant(query: str, docs: list, threshold: int = 1) -> bool:
    q_words = set(w for w in jieba.cut(query) if len(w) > 1 and w not in _QUESTION_STOP)
    if not q_words: return True
    hits = 0
    for d in docs:
        content = d.page_content if hasattr(d, 'page_content') else str(d)
        if any(w in content for w in q_words):
            hits += 1
            if hits >= threshold: return True
    return False


@router.post("/api/qa", response_model=QAResponse)
async def run_qa(req: QARequest, state: AppState = Depends(get_app_state)):
    t0 = time.time()
    cleaned = clean_query(req.question)
    k = 8 if is_brand_comparison(cleaned) else 5

    docs = await state.hybrid_retriever.ahybrid_search(
        cleaned, k=k, bm25_k=max(40, k * 5), final_k=k
    )

    # 相关性门禁
    if docs and not _any_relevant(cleaned, docs):
        elapsed = round(time.time() - t0, 2)
        return QAResponse(success=True, question=req.question, answer=_NO_DATA, elapsed=elapsed)

    # Rerank 重排序
    from src.config import RERANKER_THRESHOLD
    scores = await state.reranker.arerank(cleaned, docs)
    scored = sorted(
        [(d, s) for d, s in zip(docs, scores) if s >= RERANKER_THRESHOLD],
        key=lambda x: x[1], reverse=True
    )
    docs = [d for d, _ in scored] if scored else docs[:5]

    context = "\n---\n".join(
        f"[文档{i+1}] {d.page_content}" for i, d in enumerate(docs)
    ) if docs else "暂无相关文档"

    prompt = get_prompt_loader().load("gen_answer", "v2")
    msg = prompt.format_messages(context=context, question=req.question)
    llm = ChatOpenAI(**LLM_CONFIG)
    resp = await llm.ainvoke(msg)

    elapsed = round(time.time() - t0, 2)
    return QAResponse(success=True, question=req.question, answer=resp.content.strip(), elapsed=elapsed)
