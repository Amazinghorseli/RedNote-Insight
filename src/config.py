
"""
src/config.py — 类型安全配置管理
==================================
基于 pydantic-settings，自动从 .env / 环境变量读取。
IDE 自动补全，类型错误启动时报错而非运行时炸。
"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """应用配置，自动读取 .env 文件"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ===== LLM 配置 =====
    llm_model: str = Field(
        default="deepseek-ai/DeepSeek-V3",
        description="LLM 模型名（OpenAI 兼容格式）",
    )
    llm_temperature: float = Field(
        default=0.0,
        ge=0.0, le=2.0,
        description="生成温度（0=确定性，2=最随机）",
    )
    openai_api_key: str = Field(
        ...,  # ← 三个点 = 必填，没有就启动报错
        alias="OPENAI_API_KEY",
        description="API Key（SiliconFlow / DeepSeek / OpenAI）",
    )
    openai_base_url: str = Field(
        default="https://api.siliconflow.cn/v1",
        alias="OPENAI_BASE_URL",
        description="API Base URL",
    )

    # ===== Embedding 配置 =====
    embedding_model: str = Field(
        default="BAAI/bge-m3",
        alias="EMBEDDING_MODEL",
        description="Embedding 模型名",
    )

    # ===== Reranker 配置 =====
    reranker_model: str = Field(
        default="BAAI/bge-reranker-v2-m3",
        alias="RERANKER_MODEL",
        description="Reranker 模型名",
    )
    reranker_threshold: float = Field(
        default=0.1,
        ge=0.0, le=1.0,
        description="相关性阈值，低于此分视为不相关",
    )

    # ===== RAG 参数 =====
    retry_limit: int = Field(
        default=2,
        ge=0, le=5,
        description="自纠错最大重试次数",
    )
    top_k: int = Field(
        default=3,
        ge=1, le=20,
        description="检索返回文档数",
    )

    # ===== CORS 配置 =====
    cors_origins: list[str] = Field(
        default=["*"],
        description="允许的跨域来源",
    )

    # ===== 数据库配置 =====
    database_url: str = Field(
        default="",
        alias="DATABASE_URL",
        description="PostgreSQL 连接串（asyncpg 格式，为空则使用本地 ChromaDB）",
    )

    # ===== Redis 配置 =====
    redis_url: str = Field(
        default="",
        alias="REDIS_URL",
        description="Redis 连接串（为空则跳过缓存/限流）",
    )

    # ===== LangFuse 可观测性 =====
    langfuse_public_key: str = Field(
        default="",
        alias="LANGFUSE_PUBLIC_KEY",
        description="LangFuse Public Key",
    )
    langfuse_secret_key: str = Field(
        default="",
        alias="LANGFUSE_SECRET_KEY",
        description="LangFuse Secret Key",
    )
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        alias="LANGFUSE_HOST",
        description="LangFuse 服务地址",
    )

    # ===== 限流配置 =====
    rate_limit_enabled: bool = Field(
        default=False,
        alias="RATE_LIMIT_ENABLED",
        description="是否启用限流",
    )

    # ===== 日志配置 =====
    log_level: str = Field(
        default="INFO",
        description="日志级别（DEBUG / INFO / WARNING / ERROR）",
    )
    log_format: str = Field(
        default="console",
        description="日志格式（console=彩色可读 / json=结构化）",
    )


# ── 单例 ──────────────────────────────────────────
settings = Settings()


# ============================================================
#  向下兼容：保持原有导出，所有现有 import 不受影响
# ============================================================

LLM_CONFIG = {
    "model": settings.llm_model,
    "temperature": settings.llm_temperature,
    "api_key": settings.openai_api_key,
    "base_url": settings.openai_base_url,
}

EMBEDDING_CONFIG = {
    "model": settings.embedding_model,
    "api_key": settings.openai_api_key,
    "base_url": settings.openai_base_url,
}

RERANKER_CONFIG = {
    "model": settings.reranker_model,
    "api_key": settings.openai_api_key,
    "base_url": settings.openai_base_url,
}

RERANKER_THRESHOLD = settings.reranker_threshold
RETRY_LIMIT = settings.retry_limit
TOP_K = settings.top_k

# 路径（保持与旧版兼容）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma_db")
