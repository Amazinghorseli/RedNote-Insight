"""
database.py — PostgreSQL + pgvector 异步数据库层
=====================================================
基于 SQLAlchemy 2.0 async + asyncpg，管理 pgvector 向量存储。

用法:
    from src.core.database import get_db, init_db, DocumentTable

    await init_db()                           # 建表
    async for session in get_db():            # 获取会话
        ...
"""

import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

from sqlalchemy import Column, String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector

from src.config import settings
from src.logger import logger

# ===== SQLAlchemy Base =====
Base = declarative_base()

# ===== 引擎 & 会话工厂 =====
_engine = None
_session_factory: Optional[async_sessionmaker] = None


def _get_database_url() -> str:
    """获取 DATABASE_URL，如果未配置则使用默认值"""
    if settings.database_url:
        return settings.database_url
    return "postgresql+asyncpg://postgres:postgres@localhost:5432/rednote_insight"


def get_engine():
    """获取（懒初始化）SQLAlchemy async engine"""
    global _engine
    if _engine is None:
        url = _get_database_url()
        _engine = create_async_engine(
            url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,  # 检查连接有效性
        )
        logger.info("database_engine_created", pool_size=10)
    return _engine


def get_session_factory() -> async_sessionmaker:
    """获取会话工厂"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """异步数据库会话生成器（用于 FastAPI Depends）"""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ===== 数据表定义 =====

class DocumentTable(Base):
    """文档向量表 — 替代 ChromaDB collection"""

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    # BGE-M3 embedding = 1024 维
    embedding = Column(Vector(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 索引
    __table_args__ = (
        Index("ix_documents_created_at", "created_at"),
        Index(
            "ix_documents_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 200},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self):
        source = self.metadata_.get("source", "?") if self.metadata_ else "?"
        return f"<Document {self.id} source={source[:30]}>"


# ===== 数据库初始化 =====

async def init_db() -> None:
    """创建所有表和索引（幂等：已存在的表不会重建）"""
    engine = get_engine()
    async with engine.begin() as conn:
        # 确保 pgvector 扩展已启用
        await conn.run_sync(lambda sync_conn: sync_conn.execute(
            "CREATE EXTENSION IF NOT EXISTS vector"
        ))
        # 创建所有表
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_initialized", tables=["documents"])


async def drop_db() -> None:
    """删除所有表（危险！仅用于测试/重置）"""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("database_dropped")


# ===== 向量操作辅助 =====

async def insert_documents(
    session: AsyncSession,
    chunks: list,
    embeddings: list[list[float]],
) -> int:
    """批量插入文档向量

    Args:
        session: 数据库会话
        chunks: Document 对象列表（langchain_core.documents.Document）
        embeddings: 对应的 embedding 向量列表
    Returns:
        插入的文档数
    """
    rows = []
    for chunk, emb in zip(chunks, embeddings):
        rows.append(DocumentTable(
            content=chunk.page_content,
            metadata_=chunk.metadata,
            embedding=emb,
        ))

    session.add_all(rows)
    await session.flush()
    logger.info(f"inserted_documents", count=len(rows))
    return len(rows)


async def search_by_vector(
    session: AsyncSession,
    query_embedding: list[float],
    k: int = 5,
) -> list[dict]:
    """按余弦相似度搜索 Top-K 最相关文档

    Args:
        session: 数据库会话
        query_embedding: 查询向量 (1024 维)
        k: 返回数量
    Returns:
        [{"content": ..., "metadata": ..., "score": ...}, ...]
    """
    from sqlalchemy import text

    # pgvector 的余弦距离算子: <=>
    result = await session.execute(
        text("""
            SELECT content, metadata, 1 - (embedding <=> :query) AS score
            FROM documents
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> :query
            LIMIT :k
        """),
        {"query": query_embedding, "k": k},
    )

    rows = result.fetchall()
    return [
        {"content": row[0], "metadata": row[1], "score": float(row[2])}
        for row in rows
    ]


async def get_document_count(session: AsyncSession) -> int:
    """获取文档总数"""
    from sqlalchemy import text
    result = await session.execute(text("SELECT COUNT(*) FROM documents"))
    return result.scalar() or 0
