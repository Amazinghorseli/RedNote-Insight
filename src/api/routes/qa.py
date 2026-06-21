"""qa.py — QA 问答端点"""
import time
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import get_app_state
from src.core.state import AppState

router = APIRouter(tags=["qa"])


class QARequest(BaseModel):
    question: str
    strategy: str = "hybrid"


class QAResponse(BaseModel):
    success: bool
    question: str
    answer: str
    elapsed: float


@router.post("/api/qa", response_model=QAResponse)
async def run_qa(req: QARequest, state: AppState = Depends(get_app_state)):
    t0 = time.time()
    answer = await _run_qa(req.question, state, req.strategy)
    elapsed = round(time.time() - t0, 2)
    return QAResponse(success=True, question=req.question, answer=answer, elapsed=elapsed)


async def _run_qa(question: str, state: AppState, strategy: str = "hybrid") -> str:
    """执行 QA 管道（全异步，graph.ainvoke()）"""
    result = await state.graph.ainvoke({
        "question": question,
        "rewritten_question": "",
        "strategy": strategy if strategy != "auto" else "",
        "documents": [],
        "relevant_docs": [],
        "generation": "",
        "retry_count": 0,
    })
    response = result["generation"]
    if "无法回答" in response or "根据现有资料" in response:
        result = await state.graph.ainvoke({
            "question": question,
            "rewritten_question": "",
            "strategy": "hybrid",
            "documents": [],
            "relevant_docs": [],
            "generation": "",
            "retry_count": 0,
        })
        response = result["generation"]
    return response
