"""
main.py — FastAPI 应用组装
============================
将各路由模块注册到 app，配置生命周期、中间件和静态文件托管。

启动: uv run uvicorn src.api.main:app --port 8000
"""
import sys
import os
import uuid
import traceback
from pathlib import Path
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import settings
from src.core.state import init_app_state
from src.api.routes import health, qa, insight, evaluate, crawl, qa_stream, insight_stream


# ===== 中间件 =====

class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个请求注入 X-Request-ID，绑定到 structlog"""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        structlog.contextvars.clear_contextvars()
        return response


async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器：统一返回 JSON 格式"""
    from starlette.exceptions import HTTPException as StarletteException

    if isinstance(exc, StarletteException):
        status_code = exc.status_code
        detail = str(exc.detail)
    else:
        status_code = 500
        detail = "Internal Server Error"
        if settings.log_format == "console":
            traceback.print_exc()

    logger = structlog.get_logger()
    logger.error(
        "unhandled_exception",
        status_code=status_code,
        error_type=type(exc).__name__,
        error_message=str(exc),
        path=request.url.path,
    )

    return JSONResponse(
        status_code=status_code,
        content={
            "error": True,
            "message": detail,
            "type": type(exc).__name__,
            "request_id": request.headers.get("X-Request-ID", ""),
        },
    )


# ===== 生命周期 =====

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化 AppState，关闭时清理"""
    logger = structlog.get_logger()
    logger.info("initializing_runtime")
    app.state.app_state = await init_app_state()
    state = app.state.app_state
    if state.error:
        logger.warning("runtime_warning", error=state.error)
    else:
        logger.info("runtime_ready", chunks=state.stats["total_chunks"])
    yield
    logger.info("shutting_down")


# ===== 应用实例 =====

app = FastAPI(
    title="小红书爆款雷达 API",
    description="翻评论、找痛点、定方向 — AI 选品洞察引擎",
    version="2.0.0",
    lifespan=lifespan,
)

# ---- 注册限流（可选，需 slowapi）----
if settings.rate_limit_enabled:
    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.util import get_remote_address
        from slowapi.errors import RateLimitExceeded

        limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        import structlog
        structlog.get_logger().info("rate_limit_enabled")
    except ImportError:
        import structlog
        structlog.get_logger().warning("rate_limit_skipped", reason="slowapi_not_installed")

# ---- 注册中间件（顺序重要）----
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(Exception, global_exception_handler)

# ---- 注册路由 ----
app.include_router(health.router)
app.include_router(qa.router)
app.include_router(insight.router)
app.include_router(qa_stream.router)
app.include_router(insight_stream.router)
app.include_router(evaluate.router)
app.include_router(crawl.router)

# ---- 静态文件托管 ----
static_dir = Path(__file__).parent.parent.parent / "static"


@app.get("/")
async def serve_frontend():
    return FileResponse(static_dir / "index.html")


if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


if __name__ == "__main__":
    import uvicorn
    print("RedNote Insight API starting...")
    print("   API:   http://localhost:8000")
    print("   Front: http://localhost:8000")
    print("   Docs:  http://localhost:8000/docs")
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
