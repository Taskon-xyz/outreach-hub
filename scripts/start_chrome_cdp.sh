#!/usr/bin/env bash
# 一键启动：Chrome CDP + Python 应用（macOS）
#
# 智能默认（开箱即用，最简化用户操作）：
#   - 隔离 profile 已有登录态 → 直接启动（零拷贝，秒起）
#   - 隔离 profile 为空        → 自动从日常 Chrome 拷贝登录态（需日常 Chrome 已退出）
#   一次拷贝后永久复用，X 视你为老用户，绕开「新设备首次登录被风控」。
#
# Chrome 136+ 安全限制：--user-data-dir 指向默认 profile（用户日常 Chrome）时，
# --remote-debugging-port 被静默禁用。所以本脚本始终用项目本地的隔离 profile。
#
# 用法：
#   ./start_chrome_cdp.sh                 # 默认：智能（空白则自动同步，有则复用）
#   ./start_chrome_cdp.sh --refresh       # 强制重新拷贝（日常 Chrome 改密码/换号后用一次）
#   ./start_chrome_cdp.sh --profile NAME  # 显式指定源 profile（如 "Default" / "Profile 1"）
#   ./start_chrome_cdp.sh --no-system     # 不拷贝，纯空白 profile（调试/手动登录用）
#   ./start_chrome_cdp.sh --system        # 向后兼容别名（默认即智能同步，无需手动加）
set -euo pipefail
cd "$(dirname "$0")/.."

PORT=9222
PROJECT_ROOT="$(pwd)"
USER_DATA="$PROJECT_ROOT/data/chrome_cdp_session"
SYSTEM_PROFILE="$HOME/Library/Application Support/Google/Chrome"
INIT_FLAG="$USER_DATA/.initialized"
# 是否已初始化只看 .initialized 标志（同步成功才写）。不再用 cookies 文件大小
# 判断——登录失败时 X 也会写大量 guest cookies，会误判「已登录」而跳过同步。

# -- 0. 解析参数 --------------------------------------------------------------
MODE="auto"            # auto | refresh | nosystem
EXPLICIT_PROFILE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --refresh)         MODE="refresh"; shift ;;
        --no-system|-n)    MODE="nosystem"; shift ;;
        --system|-s)       MODE="auto"; shift ;;   # 兼容旧用法：默认已智能同步
        --profile)         EXPLICIT_PROFILE="$2"; shift 2 ;;
        --help|-h)
            cat <<EOF
用法：$0 [--refresh] [--no-system] [--profile NAME]

  （默认）           智能模式：隔离 profile 空白则自动同步日常 Chrome 登录态，
                     已有登录态则直接复用
  --refresh          强制重新拷贝（即使已初始化；日常 Chrome 改密码/换号后用一次）
  --no-system        不拷贝，纯空白 profile（调试/手动登录用，首次可能被 X 风控）
  --profile NAME     显式指定源 profile（如 "Default" / "Profile 1"），跳过自动扫描
  --system           向后兼容（默认即智能同步，加不加效果一样）

  首次自动同步需要日常 Chrome 完全退出（⌘Q），否则 cookies SQLite 持写锁拷出来会损坏。
EOF
            exit 0 ;;
        *) echo "未知参数：$1（用 --help 查看）"; exit 1 ;;
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

# -- 2. 决定是否需要拷贝 ------------------------------------------------------
# nosystem → 永不拷贝；refresh → 一定拷贝；auto → 仅当隔离 profile 空白时拷贝
NEED_COPY=0
if [ "$MODE" != "nosystem" ]; then
    if [ "$MODE" = "refresh" ]; then
        NEED_COPY=1
        echo "[--refresh] 强制重新拷贝日常 Chrome 登录态..."
    elif [ ! -f "$INIT_FLAG" ]; then
        # 没有 .initialized 标志 = 首次 / 上次未成功同步 → 需要拷贝
        NEED_COPY=1
    fi
fi

# -- 3. 从日常 Chrome 拷贝登录态（需要时）-------------------------------------
if [ $NEED_COPY -eq 1 ]; then
    if [ ! -d "$SYSTEM_PROFILE" ]; then
        echo "❌  未找到日常 Chrome profile 目录：$SYSTEM_PROFILE"
        echo "    请先用 Chrome 登录 https://x.com，⌘Q 退出后重跑。"
        echo "    或用 --no-system 纯空白启动（首次登录可能被 X 风控）。"
        exit 1
    fi

    # 日常 Chrome 在跑会持有 cookies SQLite 的写锁，拷贝出来是损坏的
    if pgrep -x "Google Chrome" > /dev/null 2>&1; then
        echo "⚠️  检测到日常 Chrome 正在运行。"
        echo "    首次同步登录态需要完全退出 Chrome（⌘Q，不只是关窗口），"
        echo "    否则 cookies 文件被占用，拷出来会损坏。"
        echo ""
        while pgrep -x "Google Chrome" > /dev/null 2>&1; do
            read -r -p $'已完全退出 Chrome？按回车继续（⌘+C 取消）...' _
        done
    fi

    # 选择源 profile：--profile 指定 / 自动扫描 auth_token
    SELECTED_PROFILE=""
    if [ -n "$EXPLICIT_PROFILE" ]; then
        if [ ! -d "$SYSTEM_PROFILE/$EXPLICIT_PROFILE" ]; then
            echo "❌  指定的 profile 不存在：$SYSTEM_PROFILE/$EXPLICIT_PROFILE"
            exit 1
        fi
        SELECTED_PROFILE="$EXPLICIT_PROFILE"
        echo "  使用指定 profile：$SELECTED_PROFILE"
    else
        echo "  扫描所有 Chrome profile，查找含 X auth_token 的那个..."
        FOUND_PROFILES=()
        # 遍历 Default + Profile N
        for profile_dir in "$SYSTEM_PROFILE/Default" "$SYSTEM_PROFILE"/Profile\ *; do
            [ -d "$profile_dir" ] || continue
            pname=$(basename "$profile_dir")
            # cookies DB 优先 Network/Cookies（Chrome 96+），fallback 老位置
            cookie_db=""
            if [ -f "$profile_dir/Network/Cookies" ]; then
                cookie_db="$profile_dir/Network/Cookies"
            elif [ -f "$profile_dir/Cookies" ]; then
                cookie_db="$profile_dir/Cookies"
            fi
            [ -n "$cookie_db" ] || continue
            # 拷一份 DB 再查（避免临时锁影响）
            tmp_db=$(mktemp)
            cp -f "$cookie_db" "$tmp_db" 2>/dev/null || { rm -f "$tmp_db"; continue; }
            has_auth=$(sqlite3 "$tmp_db" \
                "SELECT COUNT(*) FROM cookies WHERE name='auth_token' AND host_key LIKE '%.x.com' OR host_key LIKE '%.twitter.com';" \
                2>/dev/null || echo 0)
            rm -f "$tmp_db"
            if [ "${has_auth:-0}" != "0" ]; then
                FOUND_PROFILES+=("$pname")
                echo "    ✓ $pname (含 X auth_token)"
            fi
        done
        if [ ${#FOUND_PROFILES[@]} -eq 0 ]; then
            echo "❌  在所有 Chrome profile 中都没找到 X auth_token。"
            echo "    请先打开日常 Chrome 登录 https://x.com，⌘Q 退出后重试。"
            echo "    （X 首次登录请务必在日常 Chrome 里做，别在脚本启动的隔离 Chrome 里登，"
            echo "     否则会被判为新设备触发风控。）"
            exit 1
        elif [ ${#FOUND_PROFILES[@]} -gt 1 ]; then
            echo "❌  多个 profile 含 X 登录态：${FOUND_PROFILES[*]}"
            echo "    请用 --profile NAME 显式指定，例如："
            echo "      $0 --refresh --profile \"${FOUND_PROFILES[0]}\""
            exit 1
        fi
        SELECTED_PROFILE="${FOUND_PROFILES[0]}"
        echo "  自动选中：$SELECTED_PROFILE"
    fi

    # Chrome 用 OSCrypt 加密 cookies，Local State 存了加密元数据，
    # 主密钥在 macOS Keychain 里（per-app，不需要拷贝）。
    # 源 profile 文件名可能含空格（"Profile 1"），所以用变量包裹路径。
    # 目标永远是隔离 profile 的 Default/，让 Chrome 当默认 profile 用。
    SRC="$SYSTEM_PROFILE/$SELECTED_PROFILE"
    DST="$USER_DATA/Default"
    mkdir -p "$DST/Network" "$DST/Local Storage/leveldb" "$DST/Session Storage" "$DST/IndexedDB"
    copied=0
    skipped=0

    # --- 全局文件（在 profile 父目录）---
    for f in "Local State" "First Run"; do
        if [ -f "$SYSTEM_PROFILE/$f" ]; then
            cp -f "$SYSTEM_PROFILE/$f" "$USER_DATA/$f"
            copied=$((copied + 1))
        fi
    done

    # --- 文件：认证、指纹、历史 ---
    for src_rel in \
        "Cookies" \
        "Cookies-journal" \
        "Network/Cookies" \
        "Network/Cookies-journal" \
        "Preferences" \
        "Secure Preferences" \
        "Login Data" \
        "Login Data-journal" \
        "Web Data" \
        "Web Data-journal" \
        "History" \
        "History-journal" \
        "Favicons" \
        "Favicons-journal" \
        "Top Sites" \
        "Top Sites-journal" \
        "Bookmarks" \
        "Visited Links"
    do
        src_path="$SRC/$src_rel"
        dst_path="$DST/$src_rel"
        if [ -f "$src_path" ]; then
            cp -f "$src_path" "$dst_path"
            copied=$((copied + 1))
        else
            skipped=$((skipped + 1))
        fi
    done

    # --- 目录：LocalStorage / SessionStorage / IndexedDB ---
    for dir_rel in \
        "Local Storage" \
        "Session Storage" \
        "IndexedDB"
    do
        src_dir="$SRC/$dir_rel"
        dst_dir="$DST/$dir_rel"
        if [ -d "$src_dir" ]; then
            # 用 rsync 增量拷贝，保留隔离 profile 自己产生的数据（不删除目标多余文件）
            rsync -a "$src_dir/" "$dst_dir/" 2>/dev/null
            copied=$((copied + 1))
        fi
    done

    # 标记已初始化，以后启动直接复用，不再拷贝
    touch "$INIT_FLAG"
    echo "  ✓ 已从「$SELECTED_PROFILE」同步登录态到隔离 profile：$copied 项${skipped:+（$skipped 项不存在已跳过）}"
    echo "  ✓ 以后启动自动复用，无需再次同步（日常 Chrome 改密码/换号才用 --refresh）"
fi

# -- 4. 启动 Chrome CDP（后台）------------------------------------------------
# 定位 Chrome 可执行文件：先查常见安装目录（系统级 + 用户级），再用 Spotlight 兜底
CHROME_APP=""
for candidate in \
    "/Applications/Google Chrome.app" \
    "$HOME/Applications/Google Chrome.app"; do
    [ -d "$candidate" ] && CHROME_APP="$candidate" && break
done
if [ -z "$CHROME_APP" ]; then
    found=$(mdfind "kMDItemCFBundleIdentifier == 'com.google.Chrome'" 2>/dev/null | head -1)
    [ -n "$found" ] && CHROME_APP="$found"
fi
CHROME="$CHROME_APP/Contents/MacOS/Google Chrome"
if [ ! -f "$CHROME" ]; then
    echo "未找到 Chrome。"
    echo "请安装 Google Chrome: https://www.google.com/chrome/"
    echo "或修改此脚本中的 CHROME 路径"
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
    --no-first-run \
    --no-default-browser-check \
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

if [ $NEED_COPY -eq 1 ]; then
    echo "下一步："
    echo "  ✓ 已从日常 Chrome 同步登录态到隔离 profile"
    echo "  1. 在弹出的 Chrome 中确认 https://x.com 已登录（应该已经是登录态）"
    echo "  2. 回到 outreach-hub，点击「▶ 开始发送」或「▶ 开始搜索」，再点「已登录就绪」"
    echo ""
    echo "  💡 日常 Chrome 改密码或登录新账号后，运行 --refresh 重新同步"
else
    echo "下一步："
    echo "  1. 在弹出的 Chrome 中确认 https://x.com 已登录（隔离 profile 复用上次登录态）"
    echo "  2. 回到 outreach-hub，点击「▶ 开始发送」或「▶ 开始搜索」，再点「已登录就绪」"
    echo ""
    echo "  💡 若 X 登录态失效，运行 --refresh 从日常 Chrome 重新同步"
fi
echo ""

# -- 5. 启动 Python 应用（前台）-----------------------------------------------
echo ""
echo "启动 Python 应用..."
uv run python main.py

# main.py 退出后清理 Chrome
echo "应用已退出, 关闭 Chrome CDP..."
kill $CHROME_PID 2>/dev/null || true
