"""
test_health.py — API 健康检查 + 统计端点测试
"""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    """创建测试用 FastAPI app（不启动真实服务）"""
    from src.api.main import app
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
async def test_stats_requires_app_state(app):
    """GET /api/stats — 如果 AppState 未初始化应返回 503"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/stats")
        # 未初始化时返回 503
        assert resp.status_code == 503


@pytest.mark.asyncio
async def test_frontend_served(app):
    """GET / 应返回 HTML 前端页面"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
