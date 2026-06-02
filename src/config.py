"""
config.py - 统一配置管理
所有 API Key 和模型配置从 .env 文件读取
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ===== LLM 配置 =====
LLM_CONFIG = {
    "model": os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V4-Flash"),
    "temperature": 0,
    "api_key": os.getenv("OPENAI_API_KEY"),
    "base_url": os.getenv("OPENAI_BASE_URL"),
}

# ===== Embedding 配置 =====
EMBEDDING_CONFIG = {
    "model": os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
    "api_key": os.getenv("OPENAI_API_KEY"),
    "base_url": os.getenv("OPENAI_BASE_URL"),
}

# ===== Reranker 配置 =====
RERANKER_CONFIG = {
    "model": os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"),
    "api_key": os.getenv("OPENAI_API_KEY"),
    "base_url": os.getenv("OPENAI_BASE_URL"),
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
