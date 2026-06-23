"""
test_insight.py — Insight 端点测试
"""
import pytest
from httpx import AsyncClient, ASGITransport


class MockAppState:
    is_ready = True
    error = None
    stats = {"categories": [], "total_notes": 0, "total_chunks": 0}


@pytest.fixture
def app():
    from src.api.main import app
    app.state.app_state = MockAppState()
    return app


@pytest.mark.asyncio
async def test_insight_endpoint_registered(app):
    """POST /api/insight 路由已注册"""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/insight", json={"category": "test"})
        assert resp.status_code not in [404, 422]


@pytest.mark.asyncio
async def test_insight_stream_endpoint_registered(app):
    """POST /api/insight/stream 路由已注册"""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/insight/stream", json={"category": "test"})
        assert resp.status_code not in [404, 422]


@pytest.mark.asyncio
async def test_insight_validates_input(app):
    """POST /api/insight 缺少 category 应 422"""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/insight", json={})
        assert resp.status_code == 422
