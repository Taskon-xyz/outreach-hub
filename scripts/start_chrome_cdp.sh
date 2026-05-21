#!/usr/bin/env bash
# 一键启动：Chrome CDP + Python 应用
#
# 默认：项目本地 profile（data/chrome_cdp_session/），与日常 Chrome 隔离
# --system: 复用日常 Chrome profile（~/Library/Application Support/Google/Chrome）
#           适合首次登录被 X 风控时使用，让 X 看到的是同一台老设备
#
# 用法：
#   ./scripts/start_chrome_cdp.sh                # 默认隔离 profile
#   ./scripts/start_chrome_cdp.sh --system       # 复用日常 Chrome profile
set -euo pipefail
cd "$(dirname "$0")/.."

PORT=9222
PROJECT_ROOT="$(pwd)"
DEFAULT_USER_DATA="$PROJECT_ROOT/data/chrome_cdp_session"
SYSTEM_USER_DATA="$HOME/Library/Application Support/Google/Chrome"

# -- 0. 解析参数 --------------------------------------------------------------
USE_SYSTEM=0
for arg in "$@"; do
    case "$arg" in
        --system|-s) USE_SYSTEM=1 ;;
        --help|-h)
            echo "用法：$0 [--system|-s]"
            echo "  默认：项目本地 profile，与日常 Chrome 隔离"
            echo "  --system: 复用日常 Chrome profile（X 不会判定为新设备）"
            exit 0 ;;
        *) echo "未知参数：$arg（用 --help 查看）"; exit 1 ;;
    esac
done

if [ $USE_SYSTEM -eq 1 ]; then
    USER_DATA="$SYSTEM_USER_DATA"
    MODE_DESC="日常 Chrome profile（复用登录态）"
else
    USER_DATA="$DEFAULT_USER_DATA"
    MODE_DESC="项目本地隔离 profile"
fi

echo "模式：$MODE_DESC"
echo "目录：$USER_DATA"
echo ""

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

# -- 1b. --system 模式：检测日常 Chrome 是否在跑（user-data-dir 不能并发占用）--
if [ $USE_SYSTEM -eq 1 ]; then
    # 主进程名是 "Google Chrome"，Helper 进程会带后缀，用 pgrep -x 精确匹配主进程
    if pgrep -x "Google Chrome" > /dev/null 2>&1; then
        echo ""
        echo "❌  检测到日常 Chrome 正在运行。"
        echo "    --system 模式要求 Chrome 全部退出（user-data-dir 不可并发占用）。"
        echo ""
        echo "请：完全关闭 Chrome（⌘Q 退出，不只是关窗口），然后重新运行此脚本。"
        echo ""
        exit 1
    fi
    # 顺手检查 SingletonLock（异常退出留下的残留锁文件会阻止 Chrome 启动）
    if [ -e "$USER_DATA/SingletonLock" ]; then
        echo "清理残留的 SingletonLock..."
        rm -f "$USER_DATA/SingletonLock" "$USER_DATA/SingletonCookie" "$USER_DATA/SingletonSocket"
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
LOG_FILE="$PROJECT_ROOT/data/chrome_debug.log"
mkdir -p "$(dirname "$LOG_FILE")"
"$CHROME" \
    --remote-debugging-port=$PORT \
    --remote-debugging-address=127.0.0.1 \
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
echo "Chrome 进程已启动 (PID: $CHROME_PID)，等待 CDP 端口就绪..."

# 等待 CDP 端口真正可连（最多 15 秒）。Chrome 进程起来不代表 CDP 已 listen。
CDP_READY=0
for i in $(seq 1 30); do
    if nc -z 127.0.0.1 $PORT 2>/dev/null; then
        CDP_READY=1
        break
    fi
    # 顺便检测 Chrome 进程是否还活着——异常退出就立刻报错
    if ! kill -0 $CHROME_PID 2>/dev/null; then
        echo ""
        echo "❌  Chrome 已退出（启动失败）。最近日志："
        echo "─────────────────────────────"
        tail -20 "$LOG_FILE" 2>/dev/null || echo "(无日志)"
        echo "─────────────────────────────"
        echo ""
        echo "常见原因："
        echo "  • --system 模式下日常 Chrome 还在跑（user-data-dir 冲突）"
        echo "  • user-data-dir 残留 SingletonLock"
        echo "  • Chrome 路径不对"
        exit 1
    fi
    sleep 0.5
done

if [ $CDP_READY -ne 1 ]; then
    echo ""
    echo "❌  Chrome 进程跑着，但 15 秒内 CDP 端口 $PORT 仍未就绪。"
    echo "    可能是 Chrome 卡在某个对话框（如「恢复上次会话？」「设为默认浏览器？」）。"
    echo "    请手动点掉，然后 Ctrl-C 后重新运行此脚本。"
    exit 1
fi

echo "✓ CDP 端口已就绪"
echo ""

if [ $USE_SYSTEM -eq 1 ]; then
    echo "下一步："
    echo "  ✓ 已复用日常 Chrome profile，X / Twitter 通常已是登录态"
    echo "  1. 在弹出的 Chrome 中确认 https://x.com 已登录"
    echo "  2. 回到 outreach-hub，点击「▶ 开始发送」或「▶ 开始搜索」，再点「已登录就绪」"
    echo ""
    echo "  ⚠️  本次运行期间不要再单独启动日常 Chrome（会冲突）"
    echo "       outreach-hub 退出后再启动日常 Chrome"
else
    echo "下一步："
    echo "  1. 在弹出的 Chrome 中打开 https://x.com 并登录"
    echo "  2. 登录成功后，回到 outreach-hub 程序"
    echo "  3. 点击「▶ 开始发送」或「▶ 开始搜索」，再点「已登录就绪」"
    echo "  ✓ 本次登录会保存在 data/chrome_cdp_session/，下次无需重新登录"
    echo ""
    echo "  💡 若 X 登录卡循环回首页，改用 --system 复用日常 Chrome profile"
fi
echo ""

# -- 3. 启动 Python 应用（前台）-----------------------------------------------
echo ""
echo "启动 Python 应用..."
uv run python main.py

# main.py 退出后清理 Chrome
echo "应用已退出, 关闭 Chrome CDP..."
kill $CHROME_PID 2>/dev/null || true
