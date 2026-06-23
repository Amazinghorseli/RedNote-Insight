"""
test_qa.py — QA 端点测试
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
async def test_qa_endpoint_registered(app):
    """POST /api/qa 路由已注册（可能 500 因 mock 不完整，但不能 404）"""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/qa", json={"question": "test"})
        # 404 = 路由未注册, 422 = 请求格式错误
        # 500 = mock 不完整导致内部错误（可接受）
        assert resp.status_code not in [404, 422]


@pytest.mark.asyncio
async def test_qa_stream_endpoint_registered(app):
    """POST /api/qa/stream 路由已注册"""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/qa/stream", json={"question": "test"})
        assert resp.status_code not in [404, 422]


@pytest.mark.asyncio
async def test_qa_validates_input(app):
    """POST /api/qa 缺少 question 应 422"""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/qa", json={})
        assert resp.status_code == 422
