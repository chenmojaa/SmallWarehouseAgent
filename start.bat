@echo off
rem HD 一键启动（Windows）：自动装依赖 + 启动前后端
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
  python dev.py %*
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (
    py dev.py %*
  ) else (
    echo [dev] 未找到 Python。请先安装 Python 3.10+：https://www.python.org/downloads/
    pause
    exit /b 1
  )
)
