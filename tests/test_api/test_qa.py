"""
test_qa.py — QA 端点测试
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "cleaned", "k"),
    [("收纳盒材质 123", "收纳盒材质", 5), ("收纳盒推荐", "收纳盒推荐", 8)],
)
async def test_qa_uses_hybrid_retrieval_without_a_supervisor(monkeypatch, question, cleaned, k):
    from langchain_core.documents import Document

    from src.api.routes import qa

    document = Document(page_content="收纳盒材质和收纳盒推荐")
    retriever = SimpleNamespace(ahybrid_search=AsyncMock(return_value=[document]))
    reranker = SimpleNamespace(arerank=AsyncMock(return_value=[0.9]))
    llm = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="测试回答")))
    monkeypatch.setattr(qa, "ChatOpenAI", lambda **kwargs: llm)

    response = await qa.run_qa(
        qa.QARequest(question=question),
        SimpleNamespace(hybrid_retriever=retriever, reranker=reranker),
    )

    assert response.success is True
    assert response.question == question
    assert response.answer == "测试回答"
    retriever.ahybrid_search.assert_awaited_once_with(cleaned, k=k, bm25_k=40, final_k=k)
    reranker.arerank.assert_awaited_once_with(cleaned, [document])
    llm.ainvoke.assert_awaited_once()
