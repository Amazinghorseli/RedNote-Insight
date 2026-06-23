"""crawl.py — 数据抓取端点"""
import os
import asyncio
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.api.dependencies import get_app_state
from src.core.state import AppState

router = APIRouter(tags=["crawl"])
class CrawlRequest(BaseModel):
    category: str
    count: int = 20


@router.post("/api/crawl")
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
