"""
test_qa.py — QA 端点测试（非流式 + 流式）
"""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    from src.api.main import app
    return app


@pytest.mark.asyncio
async def test_qa_endpoint_exists(app):
    """POST /api/qa 端点应存在"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/qa",
            json={"question": "测试问题", "strategy": "hybrid"},
        )
        # 503 说明端点存在但 AppState 未初始化
        # 422 说明请求格式正确但被业务逻辑拦截
        assert resp.status_code in [422, 503, 200]


@pytest.mark.asyncio
async def test_qa_stream_endpoint_exists(app):
    """POST /api/qa/stream 端点应存在"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/qa/stream",
            json={"question": "测试问题", "strategy": "hybrid"},
        )
        assert resp.status_code in [422, 503, 200]


@pytest.mark.asyncio
async def test_qa_validates_input(app):
    """POST /api/qa 应验证输入格式"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 缺少 question 字段
        resp = await client.post("/api/qa", json={})
        assert resp.status_code == 422  # Pydantic 验证失败
