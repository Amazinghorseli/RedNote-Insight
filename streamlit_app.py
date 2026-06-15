"""
streamlit_app.py — Streamlit Cloud 部署入口
============================================
在 Streamlit Cloud 部署步骤：
  1. Push 到 GitHub
  2. Streamlit Cloud 连接仓库
  3. Settings → Secrets 填入:
     OPENAI_API_KEY = "sk-xxx"
     OPENAI_BASE_URL = "https://api.siliconflow.cn/v1"
     (其他可选，已设默认值)

本地运行: streamlit run streamlit_app.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# config.py 已自动从 st.secrets 加载 API Key，直接导入即可
import app
