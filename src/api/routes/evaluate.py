"""evaluate.py — RAGAS 评估端点（全异步）"""
import time
import asyncio
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.api.dependencies import get_app_state
from src.core.state import AppState
from src.config import RERANKER_THRESHOLD

router = APIRouter(tags=["evaluate"])


class EvaluateRequest(BaseModel):
    categories: list[str] = []


@router.post("/api/evaluate")
async def run_evaluation(req: EvaluateRequest, state: AppState = Depends(get_app_state)):
    """运行 RAGAS 评估（全异步）"""
    from src.evaluation import EVALUATION_DATASET, EvalResult, CategoryEvalReport
    from statistics import mean

    test_cases = EVALUATION_DATASET
    if req.categories:
        test_cases = [c for c in test_cases if c["category"] in req.categories]

    if not test_cases:
        return JSONResponse(content={
            "success": True,
            "categories": [], "total_questions": 0,
            "ragas_scores": {}, "timing_scores": {},
            "overall_score": 0, "grade": "N/A",
        })

    category_reports = []
    all_results = []

    for cat_data in test_cases:
        cat_results = []
        for q in cat_data["queries"]:
            t0 = time.time()

            # ── QA（异步）──
            result = await state.graph.ainvoke({
                "question": q["question"], "rewritten_question": "",
                "strategy": "hybrid",
                "documents": [], "relevant_docs": [],
                "generation": "", "retry_count": 0,
            })
            answer = result["generation"]
            gen_time = (time.time() - t0) * 1000

            # ── 检索上下文（异步）──
            docs = await state.hybrid_retriever.ahybrid_search(q["question"], k=5)
            if docs:
                scores = await state.reranker.arerank(q["question"], docs)
                relevant = [d for d, s in zip(docs, scores) if s >= RERANKER_THRESHOLD]
            else:
                relevant = []

            # ── 启发式评分 ──
            context_precision = _compute_context_precision(
                q["question"], [d.page_content for d in relevant], q["ground_truth"]
            )
            context_recall = _compute_context_recall(
                q["question"], [d.page_content for d in relevant], q["ground_truth"]
            )
            faithfulness = _compute_faithfulness(
                answer, [d.page_content for d in relevant]
            )
            answer_relevancy = _compute_answer_relevancy(
                q["question"], answer, q["ground_truth"]
            )

            cat_results.append(EvalResult(
                question=q["question"],
                ground_truth=q["ground_truth"],
                answer=answer[:500],
                context_precision=context_precision,
                context_recall=context_recall,
                faithfulness=faithfulness,
                answer_relevancy=answer_relevancy,
                generation_time_ms=gen_time,
            ))
            all_results.extend(cat_results[-1:])

        category_reports.append(CategoryEvalReport(
            category=cat_data["category"],
            total_questions=len(cat_results),
            results=cat_results,
        ))

    overall = mean(r.avg_quality for r in all_results)

    return JSONResponse(content={
        "success": True,
        "categories": [r.category for r in category_reports],
        "total_questions": len(all_results),
        "ragas_scores": {
            "context_precision": round(mean(r.context_precision for r in all_results) * 100, 1),
            "context_recall": round(mean(r.context_recall for r in all_results) * 100, 1),
            "faithfulness": round(mean(r.faithfulness for r in all_results) * 100, 1),
            "answer_relevancy": round(mean(r.answer_relevancy for r in all_results) * 100, 1),
        },
        "timing_scores": {
            "avg_retrieval_ms": round(mean(r.retrieval_time_ms for r in all_results), 1),
            "avg_generation_ms": round(mean(r.generation_time_ms for r in all_results), 1),
            "total_ms": round(sum(r.generation_time_ms for r in all_results), 1),
        },
        "overall_score": round(overall, 1),
        "grade": CategoryEvalReport.grade(overall),
        "per_category": {
            r.category: {
                "score": round(r.overall_score, 1),
                "grade": CategoryEvalReport.grade(r.overall_score),
                "context_precision": round(r.avg_context_precision * 100, 1),
                "context_recall": round(r.avg_context_recall * 100, 1),
                "faithfulness": round(r.avg_faithfulness * 100, 1),
                "answer_relevancy": round(r.avg_answer_relevancy * 100, 1),
            }
            for r in category_reports
        },
    })


# ── 启发式评分函数（从 evaluation.py 移植）──

def _compute_context_precision(question: str, contexts: list[str], ground_truth: str) -> float:
    if not contexts: return 0.0
    gt_keywords = set(ground_truth.replace("。", " ").replace("，", " ").split())
    if not gt_keywords: return 0.5
    scores = []
    for ctx in contexts:
        overlap = len(gt_keywords & set(ctx[:500].split()))
        scores.append(min(overlap / max(len(gt_keywords), 1) * 2, 1.0))
    return sum(scores) / len(scores)


def _compute_context_recall(question: str, contexts: list[str], ground_truth: str) -> float:
    if not contexts: return 0.0
    gt_keywords = set(ground_truth.replace("。", " ").replace("，", " ").split())
    if not gt_keywords: return 0.5
    all_words = set()
    for ctx in contexts:
        all_words.update(ctx[:500].split())
    return min(len(gt_keywords & all_words) / len(gt_keywords) * 1.5, 1.0)


def _compute_faithfulness(answer: str, contexts: list[str]) -> float:
    if not contexts or not answer: return 0.5
    ans_words = set(w for w in answer[:500].split() if len(w) > 1)
    ctx_words = set()
    for ctx in contexts:
        ctx_words.update(w for w in ctx[:500].split() if len(w) > 1)
    if not ans_words: return 0.5
    return min(len(ans_words & ctx_words) / len(ans_words) * 1.3, 1.0)


def _compute_answer_relevancy(question: str, answer: str, ground_truth: str) -> float:
    if not answer or not ground_truth: return 0.5
    gt_words = set(ground_truth.replace("。", " ").replace("，", " ").split())
    ans_words = set(answer[:500].split())
    if not gt_words: return 0.5
    inter = len(gt_words & ans_words)
    union = len(gt_words | ans_words)
    jaccard = inter / union if union > 0 else 0
    recall = inter / len(gt_words)
    return jaccard * 0.3 + recall * 0.7
