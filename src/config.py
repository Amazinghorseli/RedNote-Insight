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

# 3. 兜底：如果都没有，用内置默认值（方便一键部署演示）
_DEFAULT_API_KEY = "sk-pzfykccdjntaspwmyhtmoiovyttlbbaqwubrgvwmkbhyoist"
_DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"

def _get(key: str, default: str = None) -> str:
    return os.getenv(key) or default or ""

# ===== LLM 配置 =====
LLM_CONFIG = {
    "model": _get("LLM_MODEL", "deepseek-ai/DeepSeek-V4-Flash"),
    "temperature": 0,
    "api_key": _get("OPENAI_API_KEY", _DEFAULT_API_KEY),
    "base_url": _get("OPENAI_BASE_URL", _DEFAULT_BASE_URL),
}

# ===== Embedding 配置 =====
EMBEDDING_CONFIG = {
    "model": _get("EMBEDDING_MODEL", "BAAI/bge-m3"),
    "api_key": _get("OPENAI_API_KEY", _DEFAULT_API_KEY),
    "base_url": _get("OPENAI_BASE_URL", _DEFAULT_BASE_URL),
}

# ===== Reranker 配置 =====
RERANKER_CONFIG = {
    "model": _get("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"),
    "api_key": _get("OPENAI_API_KEY", _DEFAULT_API_KEY),
    "base_url": _get("OPENAI_BASE_URL", _DEFAULT_BASE_URL),
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
