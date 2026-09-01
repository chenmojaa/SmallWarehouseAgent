#!/usr/bin/env bash
# HD 一键启动（macOS / Linux）：自动装依赖 + 启动前后端
set -e
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  exec python3 dev.py "$@"
elif command -v python >/dev/null 2>&1; then
  exec python dev.py "$@"
else
  echo "[dev] 未找到 Python。请先安装 Python 3.10+：https://www.python.org/downloads/"
  exit 1
fi
