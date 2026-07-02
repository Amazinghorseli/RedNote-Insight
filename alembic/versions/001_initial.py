"""001_initial — 初始迁移：documents 表 + pgvector 扩展

Revision ID: 001
Revises: None
Create Date: 2026-06-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 documents 表 + pgvector 扩展 + HNSW 索引"""

    # 1. 启用 pgvector 扩展
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. 创建 documents 表
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
    )

    # 3. 将 embedding 列转为 pgvector 类型
    # (先创建为 ARRAY(Float)，再 cast 为 vector)
    op.execute("""
        ALTER TABLE documents
        ALTER COLUMN embedding TYPE vector(1024)
        USING embedding::vector(1024)
    """)

    # 4. 创建索引
    op.create_index("ix_documents_created_at", "documents", ["created_at"])

    # HNSW 向量索引（余弦相似度）
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_documents_embedding_hnsw
        ON documents
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 200)
    """)


def downgrade() -> None:
    """回滚：删除 documents 表"""
    op.drop_index("ix_documents_embedding_hnsw", table_name="documents")
    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_table("documents")
