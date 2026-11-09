#!/usr/bin/env bash
# 一键启动：安装依赖 → 构建前端（已构建则跳过，--build 强制重建）→ 启动后端（同时托管前端页面）
# --lan：局域网模式，同一网络的其他电脑也能访问（不需要外网）
set -euo pipefail
cd "$(dirname "$0")"

command -v uv >/dev/null || { echo "未找到 uv，请先安装：https://docs.astral.sh/uv/"; exit 1; }

echo "==> 安装后端依赖"
(cd backend && uv sync --quiet)

BUILD=0; LAN=0
for a in "$@"; do case "$a" in --build) BUILD=1 ;; --lan) LAN=1 ;; esac; done
[ "$LAN" = 1 ] && HOST=0.0.0.0

if [ ! -f frontend/dist/index.html ] || [ "$BUILD" = 1 ]; then
  command -v pnpm >/dev/null || { echo "未找到 pnpm，请先安装：npm i -g pnpm"; exit 1; }
  echo "==> 构建前端"
  (cd frontend && pnpm install --silent && pnpm build)
fi

echo "==> 启动服务：http://${HOST:-127.0.0.1}:${PORT:-8000}"
if [ "${HOST:-}" = "0.0.0.0" ]; then
  echo "==> 局域网模式：同一网络的电脑可以用下面的地址访问"
  for ip in $(hostname -I 2>/dev/null || ipconfig getifaddr en0 2>/dev/null); do
    case "$ip" in *:*|127.*|169.254.*) ;; *) echo "    http://$ip:${PORT:-8000}" ;; esac
  done
  grep -Eq '^\s*AUTH_ENABLED\s*=\s*(1|true)' .env 2>/dev/null || \
    echo "    提醒：没有开启登录，局域网内任何人都能使用全部功能。多人使用请在 .env 中设置 AUTH_ENABLED=1"
fi
cd backend
exec uv run python -m uvicorn api.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
