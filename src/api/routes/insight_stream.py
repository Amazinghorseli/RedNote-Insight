"""
insight_stream.py — 选品洞察 SSE 流式端点
=============================================
POST /api/insight/stream — 逐阶段 + 逐 token 输出洞察报告

用法:
    curl -N -X POST http://localhost:8000/api/insight/stream \
      -H "Content-Type: application/json" \
      -d '{"category":"磁吸感应灯"}'
"""

import json
import time
import asyncio
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.dependencies import get_app_state
from src.core.state import AppState
from src.config import RERANKER_THRESHOLD
from src.logger import logger

router = APIRouter(tags=["insight-stream"])


class InsightStreamRequest(BaseModel):
    category: str


def _sse_event(event: str, data: dict | str) -> str:
    payload = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else data
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/api/insight/stream")
async def run_insight_stream(req: InsightStreamRequest, state: AppState = Depends(get_app_state)):
    """SSE 流式选品洞察报告"""

    async def event_stream():
        t0 = time.time()
        category = req.category

        try:
            # ── 阶段 1: 检索 ──
            yield _sse_event("stage", {"stage": "retrieve", "message": f"正在检索「{category}」相关笔记..."})
            await asyncio.sleep(0)

            from src.agents.comment_agent import CommentAnalyzer
            from src.agents.demand_agent import DemandAggregator
            from src.agents.insight_agent import InsightGenerator
            from src.crawler import CrawlerInterface

            MIN_NOTES = 10
            CRAWL_COUNT = 30

            docs = await state.hybrid_retriever.ahybrid_search(
                category, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES
            )

            if docs:
                scores = await state.reranker.arerank(category, docs)
                relevant = [doc for doc, s in zip(docs, scores) if s >= RERANKER_THRESHOLD]
            else:
                relevant = []

            yield _sse_event("stage", {
                "stage": "retrieved",
                "message": f"检索到 {len(relevant)} 篇相关笔记",
                "note_count": len(relevant),
            })
            await asyncio.sleep(0)

            # ── 阶段 2: 评论分析 ──
            yield _sse_event("stage", {"stage": "analyze", "message": "正在分析评论区数据..."})
            await asyncio.sleep(0)

            if len(relevant) >= 3:
                analyzer = CommentAnalyzer(raw_dir=state.raw_dir)
                analyses = analyzer.analyze(relevant)

                if not analyses:
                    yield _sse_event("error", {"message": "没有找到评论分析数据"})
                    return

                yield _sse_event("stage", {
                    "stage": "analyzed",
                    "message": f"分析了 {len(analyses)} 条评论",
                })
                await asyncio.sleep(0)

                # ── 阶段 3: 需求聚合 ──
                yield _sse_event("stage", {"stage": "aggregate", "message": "正在聚合需求信号..."})
                await asyncio.sleep(0)

                aggregator = DemandAggregator()
                aggregated = aggregator.aggregate(analyses)

                yield _sse_event("stage", {
                    "stage": "aggregated",
                    "message": f"识别到 {len(aggregated.get('top_complaints', []))} 个痛点",
                })
                await asyncio.sleep(0)

                # ── 阶段 4: 生成报告（逐 token 流式）──
                yield _sse_event("stage", {"stage": "generate", "message": "正在生成选品洞察报告..."})

                generator = InsightGenerator()
                try:
                    async for chunk in generator.astream(aggregated, category=category):
                        if chunk:
                            yield _sse_event("token", {"token": chunk})
                except Exception as e:
                    report = generator.generate_fallback(aggregated, category=category)
                    report += f"\n\n（注：LLM 生成失败，使用模板兜底。错误：{e}）"
                    yield _sse_event("token", {"token": report})

                yield _sse_event("stage", {"stage": "done_generate", "message": "报告生成完成"})

                notes_count = len(relevant)

            else:
                # 需要爬虫
                yield _sse_event("stage", {"stage": "crawl", "message": "知识库数据不足，正在从小红书实时抓取..."})
                await asyncio.sleep(0)

                crawler = CrawlerInterface(raw_dir=state.raw_dir)

                # 如果爬虫存在但未登录，触发交互式登录流程（SSE 长连接可等待扫码）
                if not crawler.is_available and crawler.needs_login:
                    yield _sse_event("stage", {
                        "stage": "login",
                        "message": "需要登录小红书，正在打开浏览器窗口，请在浏览器中扫码登录..."
                    })
                    await asyncio.sleep(0)

                    login_ok = await asyncio.to_thread(crawler.login, 5)
                    if not login_ok:
                        yield _sse_event("error", {
                            "message": f"知识库无「{category}」数据，且登录失败或超时。"
                        })
                        return

                    yield _sse_event("stage", {
                        "stage": "login_ok",
                        "message": "小红书登录成功，开始抓取数据..."
                    })
                    await asyncio.sleep(0)

                if not crawler.is_available:
                    yield _sse_event("error", {
                        "message": f"知识库无「{category}」数据，且爬虫不可用。"
                    })
                    return

                result = await asyncio.to_thread(crawler.crawl, category, CRAWL_COUNT)
                crawled_count = result["count"]

                if crawled_count == 0:
                    yield _sse_event("error", {"message": f"无法从小红书获取「{category}」的数据"})
                    return

                yield _sse_event("stage", {
                    "stage": "crawled",
                    "message": f"已抓取 {crawled_count} 篇笔记",
                    "crawled_count": crawled_count,
                })
                await asyncio.sleep(0)

                await state.rebuild_indexes()
                await asyncio.sleep(0.5)

                # 重新检索
                fresh_docs = await state.hybrid_retriever.ahybrid_search(
                    category, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES
                )
                fresh_scores = await state.reranker.arerank(category, fresh_docs) if fresh_docs else []
                fresh_relevant = [doc for doc, s in zip(fresh_docs, fresh_scores) if s >= RERANKER_THRESHOLD]

                if not fresh_relevant:
                    yield _sse_event("error", {
                        "message": f"已抓取 {crawled_count} 篇但检索未匹配"
                    })
                    return

                analyzer = CommentAnalyzer(raw_dir=state.raw_dir)
                analyses = analyzer.analyze(fresh_relevant)
                aggregator = DemandAggregator()
                aggregated = aggregator.aggregate(analyses)
                generator = InsightGenerator()

                async for chunk in generator.astream(aggregated, category=category):
                    if chunk:
                        yield _sse_event("token", {"token": chunk})

                notes_count = len(fresh_relevant)

            # ── 阶段 5: 完成 ──
            elapsed = round(time.time() - t0, 2)
            yield _sse_event("done", {
                "elapsed": elapsed,
                "note_count": notes_count,
            })

        except Exception as e:
            logger.error(f"insight_stream_error: {e}")
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
