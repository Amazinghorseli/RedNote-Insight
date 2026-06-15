"""
streamlit_app.py — Streamlit Cloud 部署入口
============================================
Streamlit Cloud 需要根目录有一个 streamlit_app.py。
保留原有功能，同时可作为 Streamlit Community Cloud 免费部署。

部署步骤:
  1. Push 到 GitHub
  2. 在 share.streamlit.io 连接仓库
  3. 设置 secrets:
     OPENAI_API_KEY = "sk-xxx"
     OPENAI_BASE_URL = "https://api.siliconflow.cn/v1"
"""
import sys
import os

# 如果 Streamlit Cloud 检测到 secrets，写入 .env
if not os.path.exists(".env"):
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            with open(".env", "w", encoding="utf-8") as f:
                for key in ["OPENAI_API_KEY", "OPENAI_BASE_URL", "LLM_MODEL",
                           "EMBEDDING_MODEL", "RERANKER_MODEL"]:
                    if key in st.secrets:
                        f.write(f"{key}={st.secrets[key]}\n")
    except Exception:
        pass

# 直接复用原有 Streamlit 入口
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 安全导入 — 如果 app.py 不存在，回退到 FastAPI
try:
    import app
except ImportError:
    print("app.py not found, running FastAPI mode...")
    import uvicorn
    from api import app as fastapi_app
    uvicorn.run(fastapi_app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
