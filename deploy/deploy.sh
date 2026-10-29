#!/bin/bash
# 本地一键部署 / 升级到服务器：构建前端 → 打包运行必需文件 → 上传 → 服务器端最小化安装并重启。
#   ./deploy/deploy.sh root@服务器 [.env 文件]
# 可用 SSH_OPTS 传 ssh 参数，如 SSH_OPTS="-F ~/.ssh/config"。.env 只在服务器上还没有 .env 时上传（首次部署）。
set -euo pipefail
cd "$(dirname "$0")/.."
TARGET=${1:?用法：deploy/deploy.sh root@服务器 [.env 文件]}
ENV_FILE=${2:-}
SSH_OPTS=${SSH_OPTS:-}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

if [ ! -f frontend/dist/index.html ] || [ "${BUILD:-0}" = "1" ]; then
  echo "==> 构建前端"
  (cd frontend && pnpm install --silent && pnpm build)
fi

echo "==> 打包"
{
  git ls-files -co --exclude-standard -- README.md .env.example backend/agent backend/api backend/quant \
    backend/scripts backend/pyproject.toml backend/uv.lock data/market
  find frontend/dist -type f
} | grep -v __pycache__ | sort -u > "$TMP/files"
tar czf "$TMP/quant-platform.tgz" -T "$TMP/files"
mkdir "$TMP/deploy"
cp deploy/install.sh deploy/quant-platform.service "$TMP/deploy/"
UV=$(command -v uv || true)
if [ -n "$UV" ] && [ "$(uname -sm)" = "Linux x86_64" ]; then cp "$UV" "$TMP/deploy/uv"; fi
[ -n "$ENV_FILE" ] && cp "$ENV_FILE" "$TMP/deploy/app.env"
du -sh "$TMP/quant-platform.tgz"

echo "==> 上传并安装"
REMOTE=/tmp/quant-deploy
# shellcheck disable=SC2086
ssh $SSH_OPTS "$TARGET" "rm -rf $REMOTE && mkdir -p $REMOTE && chmod 700 $REMOTE"
# shellcheck disable=SC2086
scp -q $SSH_OPTS "$TMP/quant-platform.tgz" "$TMP"/deploy/* "$TARGET:$REMOTE/"
# shellcheck disable=SC2086
ssh $SSH_OPTS "$TARGET" "bash $REMOTE/install.sh $REMOTE/quant-platform.tgz \$( [ -f $REMOTE/app.env ] && echo $REMOTE/app.env ); rm -rf $REMOTE"
