#!/bin/bash
set -e

echo ""
echo "============================================"
echo "   🎯 RedNote Insight - Quick Launcher"
echo "============================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "[ERROR] Python not found. Please install Python 3.10+"
    exit 1
fi

# Check uv
if ! command -v uv &> /dev/null; then
    echo "[INFO] Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Check .env
if [ ! -f .env ]; then
    echo "[INFO] Creating .env from .env.example..."
    cp .env.example .env
    echo "[WARNING] Please edit .env and add your SiliconFlow API key!"
    echo "         Get a free key at: https://siliconflow.cn"
fi

# Check data
if [ ! -f "data/chroma_db/chroma.sqlite3" ]; then
    echo "[INFO] Generating demo data..."
    uv run python generate_data.py
fi

# Install dependencies
echo "[INFO] Installing dependencies..."
uv sync

# Launch
echo ""
echo "============================================"
echo "   🚀 Starting RedNote Insight..."
echo "   📡 API:   http://localhost:8000"
echo "   🖥️  Web:   http://localhost:8000"
echo "   📊 Docs:  http://localhost:8000/docs"
echo "============================================"
echo ""

uv run uvicorn api:app --host 0.0.0.0 --port 8000 --reload
