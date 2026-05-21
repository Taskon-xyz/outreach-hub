#!/usr/bin/env bash
# 一键启动：Chrome CDP + Python 应用
#
# Chrome 136+ 安全限制：当 --user-data-dir 指向默认 profile（用户的日常
# Chrome）时，--remote-debugging-port 被静默禁用。所以本脚本始终用项目
# 本地的隔离 profile（data/chrome_cdp_session/），CDP 才能开。
#
# 模式：
#   默认           -- 全新隔离 profile，需在弹出的 Chrome 里手动登录 X
#   --system / -s  -- 首次启动时从日常 Chrome 拷贝 cookies/Local State，
#                     保留隔离 profile（CDP 可用）+ X 登录态（不被风控）
#   --refresh      -- 配合 --system 使用，强制重新拷贝（覆盖隔离 profile
#                     里的 cookies）。日常 Chrome 改密码后需要刷一次
set -euo pipefail
cd "$(dirname "$0")/.."

PORT=9222
PROJECT_ROOT="$(pwd)"
USER_DATA="$PROJECT_ROOT/data/chrome_cdp_session"
SYSTEM_PROFILE="$HOME/Library/Application Support/Google/Chrome"

# -- 0. 解析参数 --------------------------------------------------------------
USE_SYSTEM=0
REFRESH=0
for arg in "$@"; do
    case "$arg" in
        --system|-s) USE_SYSTEM=1 ;;
        --refresh) REFRESH=1 ;;
        --help|-h)
            cat <<EOF
用法：$0 [--system|-s] [--refresh]

  默认       项目本地隔离 profile，全新登录（首次会被 X 风控的话改用 --system）
  --system   首次启动从日常 Chrome 拷贝 cookies / Local State 到隔离 profile，
             保留 CDP 能用 + X 不当新设备。Chrome 必须已完全退出（⌘Q）
  --refresh  强制重新拷贝（即使隔离 profile 里已有 cookies）
EOF
            exit 0 ;;
        *) echo "未知参数：$arg（用 --help 查看）"; exit 1 ;;
    esac
done

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

# -- 2. --system 模式：从日常 Chrome 拷贝认证文件 ----------------------------
if [ $USE_SYSTEM -eq 1 ]; then
    if [ ! -d "$SYSTEM_PROFILE/Default" ]; then
        echo "❌  未找到日常 Chrome profile：$SYSTEM_PROFILE"
        echo "    --system 模式不可用，请先用 Chrome 登录一次 X，再重试"
        exit 1
    fi

    # 日常 Chrome 在跑会持有 cookies SQLite 的写锁，拷贝出来是损坏的
    if pgrep -x "Google Chrome" > /dev/null 2>&1; then
        echo "❌  检测到日常 Chrome 正在运行。"
        echo "    --system 拷贝认证文件前必须完全关闭日常 Chrome（⌘Q，不只是关窗口）。"
        exit 1
    fi

    # 判断是否需要拷贝：首次启动 / 用户主动 --refresh
    NEED_COPY=0
    if [ $REFRESH -eq 1 ]; then
        NEED_COPY=1
        echo "[--refresh] 强制重新拷贝 cookies..."
    elif [ ! -f "$USER_DATA/Local State" ]; then
        NEED_COPY=1
        echo "[--system] 首次启动，从日常 Chrome 拷贝登录态..."
    else
        echo "[--system] 隔离 profile 已有 Local State，跳过拷贝（用 --refresh 强制刷新）"
    fi

    if [ $NEED_COPY -eq 1 ]; then
        # Chrome 用 OSCrypt 加密 cookies，Local State 存了加密元数据，
        # 主密钥在 macOS Keychain 里（per-app，不需要拷贝）。
        # Cookies 在 Chrome 96+ 移到了 Default/Network/Cookies，老位置 Default/Cookies 兼容
        mkdir -p "$USER_DATA/Default/Network"
        copied=0
        for src_rel in \
            "Local State" \
            "Default/Cookies" \
            "Default/Cookies-journal" \
            "Default/Network/Cookies" \
            "Default/Network/Cookies-journal" \
            "Default/Preferences" \
            "Default/Login Data" \
            "Default/Login Data-journal"
        do
            if [ -f "$SYSTEM_PROFILE/$src_rel" ]; then
                cp -f "$SYSTEM_PROFILE/$src_rel" "$USER_DATA/$src_rel"
                copied=$((copied + 1))
            fi
        done
        echo "  ✓ 已拷贝 $copied 个文件到 $USER_DATA"
    fi

    # 清理残留 SingletonLock
    if [ -e "$USER_DATA/SingletonLock" ]; then
        rm -f "$USER_DATA/SingletonLock" "$USER_DATA/SingletonCookie" "$USER_DATA/SingletonSocket"
    fi
fi

# -- 3. 启动 Chrome CDP（后台）------------------------------------------------
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
        exit 1
    fi
    sleep 0.5
done

if [ $CDP_READY -ne 1 ]; then
    echo ""
    echo "❌  Chrome 进程跑着，但 15 秒内 CDP 端口 $PORT 仍未就绪。"
    if grep -q "non-default data directory" "$LOG_FILE" 2>/dev/null; then
        echo "    日志显示 Chrome 拒绝在默认 profile 上开 CDP（Chrome 136+ 安全限制）。"
        echo "    本脚本不该走到这条分支 — 请把脚本和日志贴给开发者。"
    else
        echo "    可能 Chrome 卡在某个对话框（如「恢复上次会话？」），请手动点掉重试。"
    fi
    exit 1
fi

echo "✓ CDP 端口已就绪"
echo ""

if [ $USE_SYSTEM -eq 1 ]; then
    echo "下一步："
    echo "  ✓ 已从日常 Chrome 拷贝登录态到隔离 profile"
    echo "  1. 在弹出的 Chrome 中确认 https://x.com 已登录（应该已经是登录态）"
    echo "  2. 回到 outreach-hub，点击「▶ 开始发送」或「▶ 开始搜索」，再点「已登录就绪」"
    echo ""
    echo "  💡 日常 Chrome 改密码或登录新账号后，运行 --system --refresh 重新同步"
else
    echo "下一步："
    echo "  1. 在弹出的 Chrome 中打开 https://x.com 并登录"
    echo "  2. 登录成功后，回到 outreach-hub 程序"
    echo "  3. 点击「▶ 开始发送」或「▶ 开始搜索」，再点「已登录就绪」"
    echo "  ✓ 本次登录会保存在 data/chrome_cdp_session/，下次无需重新登录"
    echo ""
    echo "  💡 若 X 登录卡循环回首页，改用 --system 从日常 Chrome 拷贝登录态"
fi
echo ""

# -- 4. 启动 Python 应用（前台）-----------------------------------------------
echo ""
echo "启动 Python 应用..."
uv run python main.py

# main.py 退出后清理 Chrome
echo "应用已退出, 关闭 Chrome CDP..."
kill $CHROME_PID 2>/dev/null || true
