@echo off
cd /d %~dp0
if not exist .env copy .env.example .env >nul
echo Building and starting Debt Collector...
docker compose up -d --build
if errorlevel 1 goto error
echo.
echo Panel: http://localhost:8000
echo API docs: http://localhost:8000/docs
echo.
docker compose ps
goto end
:error
echo.
echo Docker failed. Make sure Docker Desktop is running.
:end
pause
