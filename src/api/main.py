"""
main.py — FastAPI 应用组装
============================
将各路由模块注册到 app，配置生命周期和静态文件托管。

启动: uv run uvicorn src.api.main:app --port 8000
"""
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.state import init_app_state
from src.api.routes import health, qa, insight, evaluate, crawl


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化 AppState，关闭时清理"""
    print("[API] Initializing runtime...")
    app.state.app_state = await init_app_state()
    state = app.state.app_state
    if state.error:
        print(f"[API] WARNING: {state.error}")
    else:
        print(f"[API] READY — {state.stats['total_chunks']} chunks")
    yield
    print("[API] Shutting down")


app = FastAPI(
    title="小红书爆款雷达 API",
    description="翻评论、找痛点、定方向 — AI 选品洞察引擎",
    version="2.0.0",
    lifespan=lifespan,
)

# 注册路由
app.include_router(health.router)
app.include_router(qa.router)
app.include_router(insight.router)
app.include_router(evaluate.router)
app.include_router(crawl.router)

# 静态文件托管
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
