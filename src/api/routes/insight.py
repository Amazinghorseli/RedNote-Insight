"""insight.py — 选品洞察端点"""
import time
import asyncio
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import get_app_state
from src.core.state import AppState

router = APIRouter(tags=["insight"])


class InsightRequest(BaseModel):
    category: str


class InsightResponse(BaseModel):
    success: bool
    category: str
    report: str
    notes_count: int
    generated_count: int = 0
    elapsed: float


@router.post("/api/insight", response_model=InsightResponse)
async def run_insight(req: InsightRequest, state: AppState = Depends(get_app_state)):
    t0 = time.time()
    result = await _run_insight_async(req.category, state)
    elapsed = round(time.time() - t0, 2)
    return InsightResponse(
        success=True, category=req.category,
        report=result["report"], notes_count=result["notes_count"],
        generated_count=result["generated_count"], elapsed=elapsed,
    )


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
            # 如果爬虫存在但未登录，尝试快速登录（60秒等待）
            if crawler.needs_login:
                login_ok = await asyncio.to_thread(crawler.login, 1)
                if login_ok:
                    # 登录成功，继续抓取
                    pass
                else:
                    return {
                        "report": f"知识库无「{query}」数据，且爬虫未登录。\n\n"
                                  f"请使用流式接口（POST /api/insight/stream）触发交互式登录，\n"
                                  f"或先在命令行运行:\n"
                                  f"  uv run python src/real_crawler.py \"{query}\"\n"
                                  f"完成登录后再试。",
                        "notes_count": 0, "generated_count": 0,
                    }
            else:
                return {
                    "report": f"知识库无「{query}」数据，且爬虫不可用。\n\n"
                              f"请先在命令行运行 `uv run python src/real_crawler.py \"{query}\"` 登录并抓取数据。",
                    "notes_count": 0, "generated_count": 0,
                }

        result = await asyncio.to_thread(crawler.crawl, query, CRAWL_COUNT)
        crawled_count = result["count"]
        if crawled_count == 0:
            return {"report": f"抱歉，无法从小红书获取「{query}」的数据。", "notes_count": 0, "generated_count": 0}

        await state.rebuild_indexes()
        await asyncio.sleep(0.5)

        fresh_docs = await state.hybrid_retriever.ahybrid_search(query, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES)
        fresh_scores = await state.reranker.arerank(query, fresh_docs) if fresh_docs else []
        fresh_relevant = [doc for doc, s in zip(fresh_docs, fresh_scores) if s >= RERANKER_THRESHOLD]
        if not fresh_relevant:
            return {"report": f"已从小红书抓取 {crawled_count} 篇笔记，但检索仍未匹配。", "notes_count": 0, "generated_count": crawled_count}

        report = await _do_insight(fresh_relevant, query)
        report = f"（📥 已从小红书实时抓取「{query}」{crawled_count} 篇真实笔记）\n\n{report}"

    return {"report": report,
            "notes_count": len(relevant) if crawled_count == 0 else len(fresh_relevant),
            "generated_count": crawled_count}
