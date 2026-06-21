"""
dependencies.py — FastAPI 依赖注入
====================================
所有 API 端点通过 Depends(get_app_state) 获取 AppState。
"""
from fastapi import Request, HTTPException
from src.core.state import AppState


async def get_app_state(request: Request) -> AppState:
    """FastAPI Depends: 从 request.app.state 获取 AppState"""
    state: AppState = request.app.state.app_state
    if not state.is_ready:
        detail = state.error or "服务未就绪"
        raise HTTPException(status_code=503, detail=detail)
    return state


async def get_app_state_or_none(request: Request) -> AppState:
    """不抛 503 的版本，供内部调用方自行处理"""
    return request.app.state.app_state
