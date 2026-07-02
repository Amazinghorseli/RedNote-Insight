"""
qa_stream.py — QA 流式 SSE 端点（快速通道）
==============================================
POST /api/qa/stream — 逐 token / 逐阶段输出 QA 结果

v2: 跳过 graph 管道，直接检索 + 流式生成，速度提升 3-5x。
    去掉了 supervisor LLM 调用、reranker API 调用、rewrite 重试循环。

用法:
    curl -N -X POST http://localhost:8000/api/qa/stream \
      -H "Content-Type: application/json" \
      -d '{"question":"磁吸感应灯哪个品牌好"}'
"""

import json
import time
import re
import asyncio
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_openai import ChatOpenAI

from src.api.dependencies import get_app_state
from src.core.state import AppState
from src.config import LLM_CONFIG
from src.logger import logger
from src.core.prompt_loader import get_prompt_loader
import jieba
from src.core.query_utils import clean_query, is_brand_comparison, resolve_k, resolve_bm25_k

router = APIRouter(tags=["qa-stream"])


class QAStreamRequest(BaseModel):
    question: str
    strategy: str = "hybrid"


def _sse_event(event: str, data: dict | str) -> str:
    payload = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else data
    return f"event: {event}\ndata: {payload}\n\n"


BASE_K = 5
BRAND_K = 8


# ── 通用疑问词（不参与相关性判断）──
_QUESTION_STOP = {"哪个", "哪款", "哪家", "品牌", "推荐", "好", "什么", "怎么", "如何", "多少", "对比", "测评", "排行", "有没有", "值得", "建议", "选择", "区别"}


def _any_doc_relevant(query: str, docs: list, threshold: int = 1) -> bool:
    """快速相关性检查：至少 threshold 篇文档包含查询中的品类关键词"""
    # 只取有意义的品类词（排除通用疑问词和短词）
    q_words = set(
        w for w in jieba.cut(query)
        if len(w) > 1 and w not in _QUESTION_STOP
    )
    if not q_words:
        return True  # 全是疑问词时放行
    hits = 0
    for d in docs:
        content = d.page_content if hasattr(d, 'page_content') else str(d)
        if any(w in content for w in q_words):
            hits += 1
            if hits >= threshold:
                return True
    return False


_NO_DATA_MSG = "知识库中暂无该品类的数据。请换一个品类试试，或通过选品洞察触发实时抓取。"


@router.post("/api/qa/stream")
async def run_qa_stream(req: QAStreamRequest, state: AppState = Depends(get_app_state)):
    """SSE 流式 QA — 快速通道：直连检索 + 流式生成"""

    async def event_stream():
        t0 = time.time()
        question = req.question

        try:
            # ── 阶段 1: 清洗 ──
            cleaned = clean_query(question)
            is_brand = is_brand_comparison(cleaned)
            k = BRAND_K if is_brand else BASE_K

            yield _sse_event("stage", {"stage": "retrieve", "message": f"正在检索..."})
            await asyncio.sleep(0)

            # ── 阶段 2: 直连检索 ──
            docs = await state.hybrid_retriever.ahybrid_search(
                cleaned, k=k, bm25_k=max(40, k * 5), final_k=k
            )

            yield _sse_event("stage", {
                "stage": "retrieved",
                "message": f"检索到 {len(docs)} 篇文档",
                "doc_count": len(docs),
            })
            await asyncio.sleep(0)

            # ── 相关性门禁：无匹配时直接返回 ──
            if docs and not _any_doc_relevant(cleaned, docs, threshold=1):
                yield _sse_event("token", {"token": _NO_DATA_MSG})
                elapsed = round(time.time() - t0, 2)
                yield _sse_event("done", {"answer": _NO_DATA_MSG, "elapsed": elapsed, "doc_count": 0})
                return

            # ── 阶段 3: Rerank 重排序 ──
            yield _sse_event("stage", {"stage": "rerank", "message": "正在评估文档相关性..."})
            await asyncio.sleep(0)

            from src.config import RERANKER_THRESHOLD
            scores = await state.reranker.arerank(cleaned, docs)
            scored = sorted(
                [(d, s) for d, s in zip(docs, scores) if s >= RERANKER_THRESHOLD],
                key=lambda x: x[1], reverse=True
            )
            docs = [d for d, _ in scored] if scored else docs[:5]
            logger.info(f"rerank: {len(scored)}/{len(scores)} docs above threshold")

            yield _sse_event("stage", {
                "stage": "reranked",
                "message": f"重排序完成，保留 {len(docs)} 篇高相关文档",
                "doc_count": len(docs),
            })
            await asyncio.sleep(0)

            # ── 阶段 4: 流式生成 ──
            yield _sse_event("stage", {"stage": "generate", "message": "正在生成回答..."})

            if docs:
                context = "\n---\n".join(
                    f"[文档{i+1}] {d.page_content}" for i, d in enumerate(docs)
                )
            else:
                context = "暂无相关文档"

            loader = get_prompt_loader()
            gen_prompt = loader.load("gen_answer", "v2")
            msg = gen_prompt.format_messages(context=context, question=question)

            llm = ChatOpenAI(**LLM_CONFIG)
            full_answer = ""

            async for chunk in llm.astream(msg):
                if chunk.content:
                    token = chunk.content
                    full_answer += token
                    yield _sse_event("token", {"token": token})

            # ── 阶段 4: 完成 ──
            elapsed = round(time.time() - t0, 2)
            yield _sse_event("done", {
                "answer": full_answer,
                "elapsed": elapsed,
                "doc_count": len(docs),
            })

        except Exception as e:
            logger.error(f"qa_stream_error: {e}")
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
