#!/usr/bin/env bash
# 启动 Chrome CDP 模式（供 Playwright X DM 发送连接用）
# 只会杀掉占用 9222 端口的旧 CDP Chrome，不影响你日常使用的 Chrome
set -euo pipefail

PORT=9222
USER_DATA="/tmp/chrome-debug"

# 检查端口是否已被占用
PID=$(lsof -ti :$PORT 2>/dev/null || true)
if [ -n "$PID" ]; then
    echo "端口 $PORT 已被占用（PID: $PID），正在关闭..."
    kill $PID 2>/dev/null || true
    sleep 1
    # 确认已释放
    if lsof -ti :$PORT &>/dev/null; then
        echo "端口仍被占用，强制关闭..."
        kill -9 $(lsof -ti :$PORT) 2>/dev/null || true
        sleep 1
    fi
fi

# macOS Chrome 路径
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ ! -f "$CHROME" ]; then
    echo "✗ 未找到 Chrome：$CHROME"
    echo "  请安装 Google Chrome 或修改此脚本中的 CHROME 路径"
    exit 1
fi

echo "启动 Chrome CDP（端口 $PORT）..."
echo "  登录 Twitter 后，回到程序点击「已登录就绪」"
mkdir -p "$USER_DATA"

"$CHROME" \
    --remote-debugging-port=$PORT \
    --user-data-dir="$USER_DATA" \
    &

echo "✓ Chrome CDP 已启动（PID: $!）"
echo "  调试地址：http://localhost:$PORT"
