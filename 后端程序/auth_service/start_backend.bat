@echo off
chcp 65001 >nul
rem ============================================
rem  后端一键启动：清端口 -> 迁移 -> 启动
rem ============================================
cd /d D:\前端知识\05_网页前后端程序\后端程序\auth_service

echo [1/3] 清理 8000 端口残留进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [2/3] 数据库迁移（alembic upgrade head）...
.venv\Scripts\python.exe -m alembic upgrade head
if errorlevel 1 (
    echo 迁移失败，请检查数据库连接（PostgreSQL 是否已启动）。
    pause
    exit /b 1
)

echo [3/3] 启动后端服务 http://127.0.0.1:8000 ...
echo 按 Ctrl+C 停止。
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
