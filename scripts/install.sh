#!/usr/bin/env bash
# Outreach Hub 一键安装脚本
# 新同事只需运行：bash scripts/install.sh
set -e

cd "$(dirname "$0")/.."
echo "Outreach Hub 安装"
echo "=================="

# -- 1. 检查 Chrome --
if [[ "$OSTYPE" == "darwin"* ]]; then
    CHROME="/Applications/Google Chrome.app"
    if [ ! -d "$CHROME" ]; then
        echo ""
        echo "[需要] 请先安装 Google Chrome: https://www.google.com/chrome/"
        exit 1
    fi
    echo "[OK] Google Chrome"
fi

# -- 2. 安装 uv（如果没有） --
if ! command -v uv &>/dev/null; then
    echo ""
    echo "安装 uv 包管理器..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # 让当前 shell 能找到 uv
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        echo "[需要] 请重启终端后重新运行此脚本（uv 需要加入 PATH）"
        exit 1
    fi
fi
echo "[OK] uv $(uv --version)"

# -- 3. 安装 Python + 依赖 + Playwright --
echo ""
./scripts/install_browsers.sh

echo ""
echo "=================="
echo "安装完成！"
echo ""
echo "日常使用："
echo "  ./scripts/start_chrome_cdp.sh"
echo ""
echo "或使用 Web UI："
echo "  uv run python web_server.py"
echo "  然后浏览器打开 http://localhost:5000"
