"""
api.py — 向后兼容入口
======================
原来的启动方式 `uv run uvicorn api:app` 仍然可用。

实际应用定义在 src.api.main，避免代码重复。
"""
from src.api.main import app
