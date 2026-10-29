#!/bin/bash
# 服务器端最小化安装 / 升级（Debian / Ubuntu，root 运行）。由 deploy.sh 上传后调用，也可以手动执行：
#   bash install.sh <安装包.tgz> [.env 文件]
# 只装运行平台必需的依赖：不装 akshare（仅更新行情用）、开发工具和 Node（前端已在本地构建）。
# 升级时保留 data/app.db（模型配置、对话、回测记录）、data/results 和 .env。
set -euo pipefail
PKG=${1:?用法：install.sh <安装包.tgz> [.env 文件]}
ENV_FILE=${2:-}
APP=${APP:-/opt/quant-platform}
UNIT=/etc/systemd/system/quant-platform.service
HERE=$(cd "$(dirname "$0")" && pwd)

id quant >/dev/null 2>&1 || useradd --system --home-dir "$APP" --no-create-home --shell /usr/sbin/nologin quant
mkdir -p "$APP/bin" "$APP/data/results"

# 先删旧代码再解压，避免残留已删除的文件；数据目录不动
rm -rf "$APP/backend/agent" "$APP/backend/api" "$APP/backend/quant" "$APP/backend/scripts" "$APP/frontend/dist"
tar xzf "$PKG" -C "$APP"

# uv：优先用随包上传的二进制，否则在线安装；Python 3.12 也装在安装目录内
if [ -x "$HERE/uv" ]; then install -m 755 "$HERE/uv" "$APP/bin/uv"; fi
if [ ! -x "$APP/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$APP/bin" UV_NO_MODIFY_PATH=1 sh
fi
export UV_PYTHON_INSTALL_DIR="$APP/python" UV_CACHE_DIR="$APP/.uv-cache" UV_PYTHON_PREFERENCE=only-managed
cd "$APP/backend"
"$APP/bin/uv" python install 3.12 --quiet
"$APP/bin/uv" sync --no-default-groups --frozen --compile-bytecode --quiet
"$APP/bin/uv" cache clean --quiet || true
rm -rf "$APP/.uv-cache"

if [ -n "$ENV_FILE" ] && [ ! -f "$APP/.env" ]; then
  install -m 600 -o quant -g quant "$ENV_FILE" "$APP/.env"
fi
chown -R quant:quant "$APP/data"

install -m 644 "$HERE/quant-platform.service" "$UNIT"
systemctl daemon-reload
systemctl enable quant-platform >/dev/null
systemctl restart quant-platform

for _ in $(seq 1 60); do
  curl -sf http://127.0.0.1:8650/api/health >/dev/null && break
  sleep 1
done
curl -sf http://127.0.0.1:8650/api/health >/dev/null || { journalctl -u quant-platform -n 30 --no-pager; exit 1; }
echo "==> 平台已运行在 127.0.0.1:8650（systemctl status quant-platform 查看状态）"
du -sh "$APP"
