# =============================================================================
# RedNote Insight — 多阶段 Docker 构建
# =============================================================================
# 用法:
#   docker build -t rednote-insight .
#   docker run -p 8000:8000 --env-file .env rednote-insight
# =============================================================================

# ===== Stage 1: Builder — 装依赖 =====
FROM python:3.11-slim AS builder

WORKDIR /build

# 系统依赖（ChromaDB 需要 sqlite3, jieba 等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install --no-cache-dir uv

# 先复制依赖文件（利用 Docker 缓存层）
COPY pyproject.toml uv.lock ./

# 安装生产依赖到虚拟环境
RUN uv sync --frozen --no-dev --no-editable

# ===== Stage 2: Runtime — 最小镜像 =====
FROM python:3.11-slim AS runtime

WORKDIR /app

# 运行时系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制虚拟环境
COPY --from=builder /build/.venv /app/.venv

# 复制项目源码和配置
COPY pyproject.toml ./
COPY src/ ./src/
COPY static/ ./static/
COPY data/ ./data/
COPY .env.example ./

# 创建数据目录（如果不存在）
RUN mkdir -p /app/data/raw /app/data/chroma_db

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 启动命令
CMD [".venv/bin/uv", "run", "uvicorn", "src.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
