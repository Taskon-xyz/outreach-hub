#!/usr/bin/env bash
# Outreach Hub 一键安装脚本
#
# 使用方式（新同事直接复制到终端运行）：
#   bash <(curl -fsSL https://raw.githubusercontent.com/lukezhao-tech/outreach-hub/main/scripts/install.sh)
#
# 或先 clone 后运行：
#   git clone https://github.com/Taskon-xyz/outreach-hub.git
#   cd outreach-hub
#   bash scripts/install.sh
set -e

REPO_URL="https://github.com/lukezhao-tech/outreach-hub.git"
REPO_NAME="outreach-hub"

echo "Outreach Hub 安装"
echo "=================="

# -- 0. 确认代码目录 --
# 检测是否在 repo 内（有 .git 或 pyproject.toml）
if [ -f "pyproject.toml" ] && grep -q "outreach-hub" pyproject.toml 2>/dev/null; then
    REPO_DIR="$(pwd)"
    echo "[OK] 已在项目目录: $REPO_DIR"
else
    # curl 模式：先 clone
    if [ -d "$REPO_NAME" ]; then
        echo "[OK] 目录 $REPO_NAME 已存在，拉取最新..."
        cd "$REPO_NAME"
        git pull || true
    else
        echo "克隆仓库..."
        git clone "$REPO_URL"
        cd "$REPO_NAME"
    fi
    REPO_DIR="$(pwd)"
fi

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
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        echo "[需要] 请重启终端后重新运行此脚本（uv 需要加入 PATH）"
        exit 1
    fi
fi
echo "[OK] uv $(uv --version)"

# -- 3. 安装 Python + 依赖 + Playwright --
echo ""
bash scripts/install_browsers.sh

echo ""
echo "=================="
echo "安装完成！"
echo ""
echo "日常使用："
echo "  cd $REPO_DIR"
echo "  ./scripts/start_chrome_cdp.sh"
echo ""
echo "或使用 Web UI："
echo "  cd $REPO_DIR"
echo "  uv run python web_server.py"
echo "  然后浏览器打开 http://localhost:5000"
