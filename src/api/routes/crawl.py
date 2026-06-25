"""crawl.py — 数据抓取与登录端点"""
import os
import json
import asyncio
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from src.api.dependencies import get_app_state
from src.core.state import AppState

router = APIRouter(tags=["crawl"])


class CrawlRequest(BaseModel):
    category: str
    count: int = 20


def _sse_event(event: str, data: dict | str) -> str:
    payload = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else data
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/api/crawler/status")
async def crawler_status(state: AppState = Depends(get_app_state)):
    """查询爬虫状态"""
    from src.crawler import CrawlerInterface
    crawler = CrawlerInterface(raw_dir=state.raw_dir)
    return JSONResponse(content={
        "available": crawler.is_available,
        "needs_login": crawler.needs_login,
        "is_cloud": crawler.is_cloud,
    })


@router.post("/api/crawler/login")
async def crawler_login(state: AppState = Depends(get_app_state)):
    """
    SSE 端点：交互式小红书登录。
    打开浏览器→显示二维码→等待扫码→保存 cookie。
    """
    async def event_stream():
        from src.crawler import CrawlerInterface

        crawler = CrawlerInterface(raw_dir=state.raw_dir)

        if crawler.is_available:
            yield _sse_event("login_ok", {"message": "已经登录，无需重复操作"})
            return

        if not crawler.needs_login:
            yield _sse_event("error", {"message": f"爬虫不可用，请检查配置"})
            return

        yield _sse_event("stage", {"stage": "login", "message": "正在打开小红书登录页，请在浏览器中扫码登录..."})
        await asyncio.sleep(0)

        login_ok = await asyncio.to_thread(crawler.login, 5)
        if login_ok:
            yield _sse_event("login_ok", {"message": "小红书登录成功！"})
        else:
            yield _sse_event("error", {"message": "登录超时或失败，请重试"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
