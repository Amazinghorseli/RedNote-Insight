"""
insight_stream.py — 双报告 SSE 流式端点
=============================================
POST /api/insight/stream — 同时生成「选品报告」+「选题方案」
SSE 事件: stage / token:selection / token:creator / done

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


async def _stream_generator(gen, aggregated: dict, category: str, event_type: str):
    """流式输出单个生成器，发射 event_type 事件"""
    try:
        async for chunk in gen.astream(aggregated, category=category):
            if chunk:
                yield _sse_event(event_type, {"token": chunk})
    except Exception as e:
        report = gen.generate_fallback(aggregated, category=category)
        report += f"\n\n（注：LLM 生成失败，使用模板兜底。错误：{e}）"
        yield _sse_event(event_type, {"token": report})


async def _run_analysis_pipeline(category: str, state: AppState, MIN_NOTES=10, CRAWL_COUNT=30):
    """运行检索→分析→聚合管道，返回 (aggregated, notes_count)"""
    from src.agents.comment_agent import CommentAnalyzer
    from src.agents.demand_agent import DemandAggregator
    from src.crawler import CrawlerInterface

    docs = await state.hybrid_retriever.ahybrid_search(
        category, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES
    )
    if docs:
        scores = await state.reranker.arerank(category, docs)
        relevant = [doc for doc, s in zip(docs, scores) if s >= RERANKER_THRESHOLD]
    else:
        relevant = []

    if len(relevant) >= 3:
        analyzer = CommentAnalyzer(raw_dir=state.raw_dir)
        analyses = analyzer.analyze(relevant)
        if not analyses:
            return None, 0, False
        aggregator = DemandAggregator()
        aggregated = aggregator.aggregate(analyses)
        return aggregated, len(relevant), True
    else:
        # 爬虫兜底
        crawler = CrawlerInterface(raw_dir=state.raw_dir)
        if not crawler.is_available and crawler.needs_login:
            login_ok = await asyncio.to_thread(crawler.login, 5)
            if not login_ok:
                return None, 0, False
        if not crawler.is_available:
            return None, 0, False

        result = await asyncio.to_thread(crawler.crawl, category, CRAWL_COUNT)
        if result["count"] == 0:
            return None, 0, False

        await state.rebuild_indexes()
        await asyncio.sleep(0.5)

        fresh_docs = await state.hybrid_retriever.ahybrid_search(
            category, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES
        )
        fresh_scores = await state.reranker.arerank(category, fresh_docs) if fresh_docs else []
        fresh_relevant = [doc for doc, s in zip(fresh_docs, fresh_scores) if s >= RERANKER_THRESHOLD]
        if not fresh_relevant:
            return None, 0, False

        analyzer = CommentAnalyzer(raw_dir=state.raw_dir)
        analyses = analyzer.analyze(fresh_relevant)
        aggregator = DemandAggregator()
        aggregated = aggregator.aggregate(analyses)
        return aggregated, len(fresh_relevant), True


@router.post("/api/insight/stream")
async def run_insight_stream(req: InsightStreamRequest, state: AppState = Depends(get_app_state)):
    """SSE 流式：同时生成选品报告 + 选题方案"""

    async def event_stream():
        t0 = time.time()
        category = req.category

        try:
            from src.agents.insight_agent import InsightGenerator
            from src.agents.creator_agent import CreatorGenerator

            # ── 阶段 1: 检索 ──
            yield _sse_event("stage", {"stage": "retrieve", "message": f"正在检索「{category}」相关笔记..."})
            await asyncio.sleep(0)

            docs = await state.hybrid_retriever.ahybrid_search(category, k=10, bm25_k=40, final_k=10)
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

            # ── 阶段 2: 分析 + 聚合 ──
            aggregated, notes_count, ok = await _run_analysis_pipeline(category, state)

            if not ok or aggregated is None:
                yield _sse_event("error", {"message": f"无法获取「{category}」的分析数据，请确认品类名称或尝试其他关键词"})
                return

            yield _sse_event("stage", {
                "stage": "aggregated",
                "message": f"识别到 {len(aggregated.get('top_complaints', []))} 个痛点，{len(aggregated.get('top_purchase_intents', []))} 个需求信号",
            })
            await asyncio.sleep(0)

            # ── 阶段 3: 生成选品报告 ──
            yield _sse_event("stage", {"stage": "generate_selection", "message": "正在生成选品洞察报告..."})
            ins_gen = InsightGenerator()
            async for event in _stream_generator(ins_gen, aggregated, category, "token:selection"):
                yield event

            yield _sse_event("stage", {"stage": "selection_done", "message": "选品报告完成"})

            # ── 阶段 4: 生成选题方案 ──
            yield _sse_event("stage", {"stage": "generate_creator", "message": "正在生成选题方案..."})
            cr_gen = CreatorGenerator()
            async for event in _stream_generator(cr_gen, aggregated, category, "token:creator"):
                yield event

            yield _sse_event("stage", {"stage": "creator_done", "message": "选题方案完成"})

            # ── 完成 ──
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
