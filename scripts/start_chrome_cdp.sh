#!/usr/bin/env bash
# 一键启动：Chrome CDP + Python 应用
# 只会杀掉占用 9222 端口的旧 CDP Chrome，不影响日常使用的 Chrome
set -euo pipefail
cd "$(dirname "$0")/.."

PORT=9222
# 持久化目录：放在项目 data/ 下，重启后 X 登录态保留，无需重复登录
USER_DATA="$(cd "$(dirname "$0")/.." && pwd)/data/chrome_cdp_session"

# -- 1. 清理旧 CDP 进程 -------------------------------------------------------
PIDS=$(lsof -ti :$PORT 2>/dev/null || true)
if [ -n "$PIDS" ]; then
    echo "端口 $PORT 已被占用（PID: $(echo $PIDS | tr '\n' ' ')），正在关闭..."
    echo "$PIDS" | xargs kill 2>/dev/null || true
    sleep 1
    if lsof -ti :$PORT &>/dev/null; then
        echo "端口仍被占用，强制关闭..."
        lsof -ti :$PORT | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
fi

# -- 2. 启动 Chrome CDP（后台）------------------------------------------------
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ ! -f "$CHROME" ]; then
    echo "未找到 Chrome: $CHROME"
    echo "请安装 Google Chrome 或修改此脚本中的 CHROME 路径"
    exit 1
fi

echo "启动 Chrome CDP (端口 $PORT)..."
mkdir -p "$USER_DATA"
LOG_FILE="$USER_DATA/chrome_debug.log"
"$CHROME" \
    --remote-debugging-port=$PORT \
    --user-data-dir="$USER_DATA" \
    --disable-blink-features=AutomationControlled \
    --exclude-switches=enable-automation \
    --no-first-run \
    --no-default-browser-check \
    --disable-infobars \
    --disable-features=ChromeWhatsNewUI \
    >"$LOG_FILE" 2>&1 \
    &
CHROME_PID=$!
echo "Chrome CDP 已启动 (PID: $CHROME_PID)"
echo ""
echo "下一步："
echo "  1. 在弹出的 Chrome 中打开 https://x.com 并登录"
echo "  2. 登录成功后，回到 outreach-hub 程序"
echo "  3. 点击「▶ 开始发送」或「▶ 开始搜索」，再点「已登录就绪」"
echo "  ✓ 本次登录会保存在 data/chrome_cdp_session/，下次无需重新登录"
echo ""

# -- 3. 启动 Python 应用（前台）-----------------------------------------------
echo ""
echo "启动 Python 应用..."
uv run python main.py

# main.py 退出后清理 Chrome
echo "应用已退出, 关闭 Chrome CDP..."
kill $CHROME_PID 2>/dev/null || true
