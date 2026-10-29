#!/usr/bin/env bash
# 一键启动：安装依赖 → 构建前端（已构建则跳过，--build 强制重建）→ 启动后端（同时托管前端页面）
set -euo pipefail
cd "$(dirname "$0")"

command -v uv >/dev/null || { echo "未找到 uv，请先安装：https://docs.astral.sh/uv/"; exit 1; }

echo "==> 安装后端依赖"
(cd backend && uv sync --quiet)

if [ ! -f frontend/dist/index.html ] || [ "${1:-}" = "--build" ]; then
  command -v pnpm >/dev/null || { echo "未找到 pnpm，请先安装：npm i -g pnpm"; exit 1; }
  echo "==> 构建前端"
  (cd frontend && pnpm install --silent && pnpm build)
fi

echo "==> 启动服务：http://${HOST:-127.0.0.1}:${PORT:-8000}"
cd backend
exec uv run uvicorn api.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
