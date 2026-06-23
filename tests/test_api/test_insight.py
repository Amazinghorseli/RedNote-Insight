"""
test_insight.py — Insight 端点测试（非流式 + 流式）
"""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    from src.api.main import app
    return app


@pytest.mark.asyncio
async def test_insight_endpoint_exists(app):
    """POST /api/insight 端点应存在"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/insight",
            json={"category": "磁吸感应灯"},
        )
        assert resp.status_code in [422, 503, 200]


@pytest.mark.asyncio
async def test_insight_stream_endpoint_exists(app):
    """POST /api/insight/stream 端点应存在"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/insight/stream",
            json={"category": "磁吸感应灯"},
        )
        assert resp.status_code in [422, 503, 200]


@pytest.mark.asyncio
async def test_insight_validates_input(app):
    """POST /api/insight 应验证输入格式"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 缺少 category 字段
        resp = await client.post("/api/insight", json={})
        assert resp.status_code == 422
