"""
inspiration.py — 灵感库 API
============================
GET /api/inspiration           → 返回全部灵感
GET /api/inspiration?category=美妆 → 按品类筛选
GET /api/inspiration/categories → 列出所有品类
"""
from fastapi import APIRouter, Query

from src.data.inspiration import get_inspiration, get_categories

router = APIRouter(prefix="/api/inspiration", tags=["inspiration"])


@router.get("")
async def list_inspiration(category: str = Query(None)):
    """返回灵感列表，可选按品类筛选"""
    items = get_inspiration(category)
    return {
        "items": items,
        "total": len(items),
        "categories": get_categories(),
        "category": category or "全部",
    }


@router.get("/categories")
async def list_categories():
    """返回所有品类"""
    return {"categories": get_categories()}
