"""evaluate.py — RAGAS 评估端点"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.api.dependencies import get_app_state
from src.core.state import AppState

router = APIRouter(tags=["evaluate"])


class EvaluateRequest(BaseModel):
    categories: list[str] = []


@router.post("/api/evaluate")
async def run_evaluation(req: EvaluateRequest, state: AppState = Depends(get_app_state)):
    """运行 RAGAS 评估"""
    from src.evaluation import RAGEvaluator

    def _qa_sync(q: str, s: str = "hybrid") -> str:
        result = state.graph.invoke({
            "question": q, "rewritten_question": "",
            "strategy": s if s != "auto" else "",
            "documents": [], "relevant_docs": [],
            "generation": "", "retry_count": 0,
        })
        return result["generation"]

    evaluator = RAGEvaluator(
        qa_func=_qa_sync,
        hybrid_retriever=state.hybrid_retriever,
        reranker=state.reranker,
    )

    categories = req.categories or None
    results = evaluator.evaluate(categories=categories)

    return JSONResponse(content={
        "success": True,
        "evaluated_categories": results["categories"],
        "total_questions": results["total_questions"],
        "ragas_scores": results["ragas_scores"],
        "timing_scores": results["timing_scores"],
        "overall_score": results["overall_score"],
        "grade": results["grade"],
    })
