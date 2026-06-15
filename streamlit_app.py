"""
streamlit_app.py — Streamlit Cloud 部署入口
============================================
在 Streamlit Cloud 上部署，需要：
  1. 在 app settings → Secrets 中设置:
     OPENAI_API_KEY = "sk-xxx"
     OPENAI_BASE_URL = "https://api.siliconflow.cn/v1"
     (LLM_MODEL, EMBEDDING_MODEL, RERANKER_MODEL 有默认值，可选)
  2. 确保项目根目录有 app.py 和 data/raw/*.md

本地也能运行: streamlit run streamlit_app.py
"""
import os
import sys

# ============================================================
# 关键：在 import 任何项目模块之前，从 st.secrets 注入环境变量
# config.py 通过 os.getenv() 读取，所以必须提前设置
# ============================================================
try:
    import streamlit as st
    if hasattr(st, "secrets"):
        # 将 Streamlit Secrets 注入到 os.environ
        secret_keys = [
            "OPENAI_API_KEY", "OPENAI_BASE_URL",
            "LLM_MODEL", "EMBEDDING_MODEL", "RERANKER_MODEL",
        ]
        for key in secret_keys:
            if key in st.secrets and key not in os.environ:
                os.environ[key] = st.secrets[key]
                print(f"[streamlit_app] Loaded secret: {key}")
except Exception as e:
    print(f"[streamlit_app] Secrets not loaded: {e}")

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 直接复用原有 Streamlit 入口
try:
    import app
except ImportError:
    print("app.py not found, running FastAPI mode...")
    import uvicorn
    from api import app as fastapi_app
    uvicorn.run(fastapi_app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
