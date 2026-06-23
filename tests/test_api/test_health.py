"""
test_health.py — API 健康检查 + 统计端点测试
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from httpx import AsyncClient, ASGITransport


class MockAppState:
    """模拟已初始化的 AppState"""
    is_ready = True
    error = None
    stats = {
        "categories": ["磁吸感应灯", "桌面收纳"],
        "total_notes": 50,
        "total_chunks": 50,
    }


@pytest.fixture
def app():
    from src.api.main import app
    app.state.app_state = MockAppState()
    return app


@pytest.mark.asyncio
async def test_health_returns_200(app):
    """GET /api/health 应返回 200"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_returns_version(app):
    """GET /api/health 应包含版本号"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.json()["version"] == "2.0.0"


@pytest.mark.asyncio
async def test_stats_returns_data(app):
    """GET /api/stats 返回知识库统计"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["categories"]) == 2


@pytest.mark.asyncio
async def test_stats_503_when_not_ready():
    """GET /api/stats — 未初始化应返回 503"""
    from src.api.main import app
    # 用 not-ready 的 mock
    class NotReady:
        is_ready = False
        error = "未初始化"
    app.state.app_state = NotReady()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/stats")
        assert resp.status_code == 503


@pytest.mark.asyncio
async def test_frontend_served(app):
    """GET / 应返回 HTML 前端页面"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
