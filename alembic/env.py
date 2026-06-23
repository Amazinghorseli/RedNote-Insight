"""
alembic/env.py — Alembic 迁移环境配置
========================================
用于 PostgreSQL + pgvector 数据库迁移管理。

用法:
    uv run alembic revision --autogenerate -m "描述"
    uv run alembic upgrade head
    uv run alembic downgrade -1
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Alembic Config 对象
config = context.config

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标元数据（所有表定义）
from src.core.database import Base
target_metadata = Base.metadata


def get_url() -> str:
    """从配置文件或环境变量获取 DATABASE_URL"""
    return config.get_main_option(
        "sqlalchemy.url",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/rednote_insight",
    )


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本（不连接数据库）"""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """在线模式：连接数据库并执行迁移"""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """在线模式入口"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
