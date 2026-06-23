"""
qa_stream.py — QA 流式 SSE 端点
=================================
POST /api/qa/stream — 逐 token / 逐阶段输出 QA 结果

用法:
    curl -N -X POST http://localhost:8000/api/qa/stream \
      -H "Content-Type: application/json" \
      -d '{"question":"磁吸感应灯哪个品牌好"}'
"""

import json
import time
import asyncio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.dependencies import get_app_state
from src.core.state import AppState
from src.config import LLM_CONFIG
from langchain_openai import ChatOpenAI
from src.logger import logger
from src.core.prompt_loader import get_prompt_loader

router = APIRouter(tags=["qa-stream"])


class QAStreamRequest(BaseModel):
    question: str
    strategy: str = "hybrid"


def _sse_event(event: str, data: dict | str) -> str:
    """格式化为 SSE 事件"""
    payload = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else data
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/api/qa/stream")
async def run_qa_stream(req: QAStreamRequest, state: AppState = Depends(get_app_state)):
    """SSE 流式 QA：逐阶段输出 + 最终逐 token 生成"""

    async def event_stream():
        t0 = time.time()
        question = req.question
        strategy = req.strategy

        try:
            # ── 阶段 1: 启动 ──
            yield _sse_event("stage", {"stage": "start", "message": f"开始分析问题：{question[:50]}..."})
            await asyncio.sleep(0)

            # ── 阶段 2: Supervisor 路由 ──
            yield _sse_event("stage", {"stage": "supervisor", "message": "正在分析问题类型..."})
            await asyncio.sleep(0)

            # ── 阶段 3: 检索 ──
            yield _sse_event("stage", {"stage": "retrieve", "message": "正在检索相关文档..."})
            await asyncio.sleep(0)

            # 先跑 graph.ainvoke() 做检索和重排序
            result = await state.graph.ainvoke({
                "question": question,
                "rewritten_question": "",
                "strategy": strategy if strategy != "auto" else "",
                "documents": [],
                "relevant_docs": [],
                "generation": "",
                "retry_count": 0,
            })

            docs = result.get("relevant_docs") or result.get("documents", [])
            yield _sse_event("stage", {
                "stage": "retrieved",
                "message": f"检索到 {len(docs)} 篇相关文档",
                "doc_count": len(docs),
            })
            await asyncio.sleep(0)

            # ── 阶段 4: 生成（逐 token 流式）──
            yield _sse_event("stage", {"stage": "generate", "message": "正在生成回答..."})

            # 构建 context
            if docs:
                context = "\n---\n".join(
                    f"[文档{i+1}] {d.page_content}" for i, d in enumerate(docs)
                )
            else:
                context = "暂无相关文档"

            # 使用 YAML Prompt 格式化消息
            loader = get_prompt_loader()
            gen_prompt = loader.load("gen_answer", "v1")
            msg = gen_prompt.format_messages(context=context, question=question)

            llm = ChatOpenAI(**LLM_CONFIG)
            full_answer = ""

            async for chunk in llm.astream(msg):
                if chunk.content:
                    token = chunk.content
                    full_answer += token
                    yield _sse_event("token", {"token": token})

            # ── 阶段 5: 完成 ──
            elapsed = round(time.time() - t0, 2)
            yield _sse_event("done", {
                "answer": full_answer,
                "elapsed": elapsed,
                "doc_count": len(docs),
            })

        except Exception as e:
            logger.error(f"stream_error: {e}")
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
