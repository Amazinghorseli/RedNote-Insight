"""health.py — 健康检查 + 统计端点"""
from fastapi import APIRouter, Depends
from src.api.dependencies import get_app_state
from src.core.state import AppState

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}


@router.get("/api/stats")
async def get_stats(state: AppState = Depends(get_app_state)):
    stats = state.stats
    return {
        "success": True,
        "categories": stats["categories"],
        "total_notes": stats["total_notes"],
        "total_chunks": stats["total_chunks"],
        "message": f"知识库就绪，共 {len(stats['categories'])} 个品类",
    }
