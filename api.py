"""
api.py — 小红书爆款雷达 FastAPI 后端 (Day 3: AppState DI + async graph)
======================================================================
- AppState 替代全局 _runtime，通过 Depends 注入
- graph.ainvoke() 替代 asyncio.to_thread(graph.invoke, ...)
- 全链路异步化

启动: uv run uvicorn api:app --port 8000
"""
import os
import sys
import time
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.state import AppState, init_app_state
from src.api.dependencies import get_app_state


# ============================================================
# 请求/响应模型
# ============================================================

class InsightRequest(BaseModel):
    category: str

class QARequest(BaseModel):
    question: str
    strategy: str = "hybrid"

class EvaluateRequest(BaseModel):
    categories: list[str] = []

class CrawlRequest(BaseModel):
    category: str
    count: int = 20

class InsightResponse(BaseModel):
    success: bool
    category: str
    report: str
    notes_count: int
    generated_count: int = 0
    elapsed: float

class QAResponse(BaseModel):
    success: bool
    question: str
    answer: str
    elapsed: float

class StatsResponse(BaseModel):
    success: bool
    categories: list[str]
    total_notes: int
    total_chunks: int
    message: str


# ============================================================
# 应用生命周期
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化 AppState，关闭时清理"""
    print("[API] Initializing runtime...")
    app.state.app_state = await init_app_state()
    state = app.state.app_state
    if state.error:
        print(f"[API] WARNING: {state.error}")
    else:
        print(f"[API] READY — {state.stats['total_chunks']} chunks")
    yield
    print("[API] Shutting down")


app = FastAPI(
    title="小红书爆款雷达 API",
    description="翻评论、找痛点、定方向 — AI 选品洞察引擎",
    version="2.0.0",
    lifespan=lifespan,
)


# ============================================================
# 业务逻辑
# ============================================================

async def _run_insight_async(query: str, state: AppState) -> dict:
    """执行洞察管道（全异步）"""
    from src.agents.comment_agent import CommentAnalyzer
    from src.agents.demand_agent import DemandAggregator
    from src.agents.insight_agent import InsightGenerator
    from src.config import RERANKER_THRESHOLD
    from src.crawler import CrawlerInterface

    MIN_NOTES = 10
    CRAWL_COUNT = 30

    async def _do_insight(docs, category):
        analyzer = CommentAnalyzer(raw_dir=state.raw_dir)
        analyses = analyzer.analyze(docs)
        if not analyses:
            return "没有找到评论分析数据。"
        aggregator = DemandAggregator()
        aggregated = aggregator.aggregate(analyses)
        generator = InsightGenerator()
        try:
            report = await generator.agenerate(aggregated, category=category)
        except Exception as e:
            report = generator.generate_fallback(aggregated, category=category)
            report += f"\n\n（注：LLM 生成失败，使用模板兜底。错误：{e}）"
        return report

    docs = await state.hybrid_retriever.ahybrid_search(query, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES)
    if not docs:
        docs = []

    scores = await state.reranker.arerank(query, docs) if docs else []
    relevant = [doc for doc, s in zip(docs, scores) if s >= RERANKER_THRESHOLD]

    crawled_count = 0
    if len(relevant) >= 3:
        report = await _do_insight(relevant, query)
    else:
        crawler = CrawlerInterface(raw_dir=state.raw_dir)
        if not crawler.is_available:
            return {
                "report": f"知识库无「{query}」数据，且爬虫不可用。\n\n"
                          f"💡 请先在命令行运行 `uv run python src/real_crawler.py \"{query}\"` 登录并抓取数据。",
                "notes_count": 0,
                "generated_count": 0,
            }

        result = await asyncio.to_thread(crawler.crawl, query, CRAWL_COUNT)
        crawled_count = result["count"]

        if crawled_count == 0:
            return {
                "report": f"抱歉，无法从小红书获取「{query}」的数据。",
                "notes_count": 0,
                "generated_count": 0,
            }

        await state.rebuild_indexes()
        await asyncio.sleep(0.5)

        fresh_docs = await state.hybrid_retriever.ahybrid_search(
            query, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES
        )
        fresh_scores = await state.reranker.arerank(query, fresh_docs) if fresh_docs else []
        fresh_relevant = [doc for doc, s in zip(fresh_docs, fresh_scores) if s >= RERANKER_THRESHOLD]
        if not fresh_relevant:
            return {
                "report": f"已从小红书抓取 {crawled_count} 篇笔记，但检索仍未匹配。",
                "notes_count": 0,
                "generated_count": crawled_count,
            }

        report = await _do_insight(fresh_relevant, query)
        report = f"（📥 已从小红书实时抓取「{query}」{crawled_count} 篇真实笔记）\n\n{report}"

    return {
        "report": report,
        "notes_count": len(relevant) if crawled_count == 0 else len(fresh_relevant),
        "generated_count": crawled_count,
    }


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


# ============================================================
# API 路由（全部通过 Depends 注入 AppState）
# ============================================================

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats(state: AppState = Depends(get_app_state)):
    stats = state.stats
    return StatsResponse(
        success=True,
        categories=stats["categories"],
        total_notes=stats["total_notes"],
        total_chunks=stats["total_chunks"],
        message=f"知识库就绪，共 {len(stats['categories'])} 个品类",
    )


@app.post("/api/insight", response_model=InsightResponse)
async def run_insight(req: InsightRequest, state: AppState = Depends(get_app_state)):
    t0 = time.time()
    result = await _run_insight_async(req.category, state)
    elapsed = round(time.time() - t0, 2)

    return InsightResponse(
        success=True,
        category=req.category,
        report=result["report"],
        notes_count=result["notes_count"],
        generated_count=result["generated_count"],
        elapsed=elapsed,
    )


@app.post("/api/qa", response_model=QAResponse)
async def run_qa(req: QARequest, state: AppState = Depends(get_app_state)):
    t0 = time.time()
    answer = await _run_qa(req.question, state, req.strategy)
    elapsed = round(time.time() - t0, 2)

    return QAResponse(
        success=True,
        question=req.question,
        answer=answer,
        elapsed=elapsed,
    )


@app.post("/api/evaluate")
async def run_evaluation(req: EvaluateRequest, state: AppState = Depends(get_app_state)):
    """运行 RAGAS 评估"""
    from src.evaluation import RAGEvaluator

    def _qa_sync(q: str, s: str = "hybrid") -> str:
        result = state.graph.invoke({
            "question": q,
            "rewritten_question": "",
            "strategy": s if s != "auto" else "",
            "documents": [],
            "relevant_docs": [],
            "generation": "",
            "retry_count": 0,
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


@app.post("/api/crawl")
async def trigger_crawl(req: CrawlRequest, state: AppState = Depends(get_app_state)):
    """触发数据抓取"""
    from src.crawler import CrawlerInterface
    crawler = CrawlerInterface(raw_dir=state.raw_dir)

    result = await asyncio.to_thread(crawler.crawl, req.category, req.count)

    if result["count"] > 0:
        await state.rebuild_indexes()
        state.stats["total_notes"] = len(os.listdir(state.raw_dir))

    return JSONResponse(content={
        "success": result["count"] > 0,
        "method": result["method"],
        "count": result["count"],
        "message": f"抓取完成: {result['count']} 篇" if result["count"] > 0 else "抓取失败",
    })


# ============================================================
# 静态文件托管
# ============================================================

static_dir = Path(__file__).parent / "static"


@app.get("/")
async def serve_frontend():
    return FileResponse(static_dir / "index.html")


if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    print("RedNote Insight API starting...")
    print("   API:   http://localhost:8000")
    print("   Front: http://localhost:8000")
    print("   Docs:  http://localhost:8000/docs")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
