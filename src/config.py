"""
config.py - 统一配置管理
================================
优先从 Streamlit Secrets 读取（部署环境），
其次从 .env 文件读取（本地开发），
最后使用默认值。
"""
import os
from dotenv import load_dotenv

# 1. 先尝试从 .env 文件加载（本地开发）
load_dotenv()

# 2. 如果运行在 Streamlit Cloud，从 st.secrets 覆盖（优先级更高）
try:
    import streamlit as st
    if hasattr(st, "secrets"):
        for key in ["OPENAI_API_KEY", "OPENAI_BASE_URL",
                     "LLM_MODEL", "EMBEDDING_MODEL", "RERANKER_MODEL"]:
            if key in st.secrets:
                os.environ[key] = st.secrets[key]
except Exception:
    pass  # 本地环境没有 streamlit 也没关系

# 3. 严格模式：必须配置环境变量，不提供默认值，避免 API Key 泄露
def _get(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise ValueError(
            f"❌ 缺少环境变量 {key}。\n"
            f"   请复制 .env.example 为 .env，填入你的 API Key。\n"
            f"   Streamlit Cloud 用户在 Secrets 中配置。"
        )
    return val

# ===== LLM 配置 =====
LLM_CONFIG = {
    "model": os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V4-Flash"),
    "temperature": 0,
    "api_key": _get("OPENAI_API_KEY"),
    "base_url": _get("OPENAI_BASE_URL"),
}

# ===== Embedding 配置 =====
EMBEDDING_CONFIG = {
    "model": os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
    "api_key": _get("OPENAI_API_KEY"),
    "base_url": _get("OPENAI_BASE_URL"),
}

# ===== Reranker 配置 =====
RERANKER_CONFIG = {
    "model": os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"),
    "api_key": _get("OPENAI_API_KEY"),
    "base_url": _get("OPENAI_BASE_URL"),
}
RERANKER_THRESHOLD = 0.1  # 低于此分的文档视为不相关

# ===== 路径配置 =====
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma_db")

# ===== RAG 参数 =====
RETRY_LIMIT = 2  # 自纠错最大重试次数
TOP_K = 3  # 检索返回的文档数
