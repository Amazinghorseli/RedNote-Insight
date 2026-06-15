@echo off
chcp 65001 >nul
title RedNote Insight - Launcher

echo.
echo ============================================
echo    🎯 RedNote Insight - Quick Launcher
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

:: Check uv
uv --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing uv package manager...
    powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"
)

:: Check .env
if not exist .env (
    echo [INFO] Creating .env from .env.example...
    copy .env.example .env >nul
    echo [WARNING] Please edit .env and add your SiliconFlow API key!
    echo          Get a free key at: https://siliconflow.cn
    start notepad .env
    pause
)

:: Check data
if not exist "data\chroma_db\chroma.sqlite3" (
    echo [INFO] Generating demo data...
    uv run python generate_data.py
)

:: Install dependencies
echo [INFO] Installing dependencies...
uv sync

:: Launch
echo.
echo ============================================
echo    🚀 Starting RedNote Insight...
echo    📡 API:   http://localhost:8000
echo    🖥️  Web:   http://localhost:8000
echo    📊 Docs:  http://localhost:8000/docs
echo ============================================
echo.

uv run uvicorn api:app --host 0.0.0.0 --port 8000 --reload

pause
