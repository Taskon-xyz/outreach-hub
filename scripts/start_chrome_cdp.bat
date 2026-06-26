@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ══ Outreach Hub — Windows 版 Chrome CDP 智能启动（X 发送专用）══════════════
REM
REM 智能默认（开箱即用，最简化用户操作）：
REM   - 隔离 profile 已有登录态 → 直接启动（零拷贝，秒起）
REM   - 隔离 profile 为空        → 自动从日常 Chrome 拷贝登录态（需日常 Chrome 已退出）
REM   一次拷贝后永久复用，X 视你为老用户，绕开「新设备首次登录被风控」。
REM
REM 启动一个监听 9222 的真实 Chrome（项目本地隔离 profile），在其中登录 X。
REM 登录态保存在 data\chrome_cdp_session\，下次无需重新登录。
REM X 发送（Playwright）通过 CDP 连接这个 Chrome 来自动发 DM。
REM Telegram 发送走 web.telegram.org，无需本脚本。
REM
REM 用法：
REM   start_chrome_cdp.bat                  :: 默认：智能（空白则自动同步，有则复用）
REM   start_chrome_cdp.bat --refresh        :: 强制重新拷贝（日常 Chrome 改密码/换号后用一次）
REM   start_chrome_cdp.bat --profile NAME   :: 显式指定源 profile（如 Default / "Profile 1"）
REM   start_chrome_cdp.bat --no-system      :: 不拷贝，纯空白 profile（调试/手登用）
REM   start_chrome_cdp.bat --system         :: 向后兼容（默认即智能同步，加不加效果一样）

cd /d "%~dp0\.."

set PORT=9222
set USER_DATA=%cd%\data\chrome_cdp_session
set SRC_DIR=%LOCALAPPDATA%\Google\Chrome\User Data
set INIT_FLAG=%USER_DATA%\.initialized
REM 是否已初始化只看 .initialized 标志（同步成功才写）。不再用 cookies 文件大小
REM 判断——登录失败时 X 也会写大量 guest cookies，会误判「已登录」而跳过同步。

REM ── 0. 解析参数 ──────────────────────────────────────────────────────────────
set MODE=auto
set EXPLICIT_PROFILE=
:parse
if "%~1"=="" goto parsed
if /i "%~1"=="--refresh"    (set "MODE=refresh"   & shift & goto parse)
if /i "%~1"=="--no-system"  (set "MODE=nosystem"  & shift & goto parse)
if /i "%~1"=="--system"     (set "MODE=auto"      & shift & goto parse)
if /i "%~1"=="--help"       goto :usage
if /i "%~1"=="-h"           goto :usage
if /i "%~1"=="--profile" (
    set "EXPLICIT_PROFILE=%~2"
    shift & shift & goto parse
)
echo 未知参数：%~1（用 --help 查看）
exit /b 1
:parsed

REM ── 1. 定位 Chrome ──────────────────────────────────────────────────────────
set CHROME=
for %%P in (
    "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
    "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
    "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
) do (
    if exist "%%~P" set "CHROME=%%~P"
)
if "%CHROME%"=="" (
    echo [错误] 未找到 Google Chrome，请先安装：https://www.google.com/chrome/
    pause
    exit /b 1
)

REM ── 2. 关闭占用 9222 的旧进程 ───────────────────────────────────────────────
for /f "tokens=5" %%a in ('netstat -ano -p tcp ^| findstr ":9222 " ^| findstr "LISTENING"') do (
    echo 关闭占用 %PORT% 的旧进程 PID=%%a
    taskkill /F /PID %%a >nul 2>&1
)

REM ── 3. 决定是否拷贝登录态 ───────────────────────────────────────────────────
REM nosystem → 永不拷贝；refresh → 一定拷贝；auto → 仅当隔离 profile 空白时拷贝
set NEED_COPY=0
if "%MODE%"=="nosystem" goto decided

if "%MODE%"=="refresh" (
    set "NEED_COPY=1"
    echo [--refresh] 强制重新拷贝日常 Chrome 登录态...
    goto decided
)

REM auto：没有 .initialized 标志就同步（首次 / 上次未成功同步）
set NEED_COPY=1
if exist "%INIT_FLAG%" set "NEED_COPY=0"

:decided

REM ── 4. 拷贝登录态（需要时）──────────────────────────────────────────────────
if "%NEED_COPY%"=="1" (
    call :do_copy
    if errorlevel 1 (
        echo.
        echo [错误] 同步登录态失败，请按上面提示处理。
        pause
        exit /b 1
    )
) else (
    echo [OK] 隔离 profile 已有登录态，直接启动（用 --refresh 强制重新同步）
)

REM ── 5. 启动 Chrome CDP（后台新窗口）────────────────────────────────────────
echo 启动 Chrome CDP（端口 %PORT%）...
if not exist "data" mkdir "data"
start "" "%CHROME%" ^
    --remote-debugging-port=%PORT% ^
    --remote-debugging-address=127.0.0.1 ^
    --user-data-dir="%USER_DATA%" ^
    --no-first-run ^
    --no-default-browser-check

REM ── 6. 等待 CDP 端口就绪（最多 ~15 秒）──────────────────────────────────────
echo 等待 CDP 端口就绪...
set READY=0
for /l %%i in (1,1,30) do (
    powershell -NoProfile -Command "try{(Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 'http://127.0.0.1:9222/json/version')|Out-Null; exit 0}catch{exit 1}" >nul 2>&1
    if !errorlevel!==0 (
        set READY=1
        goto :cdpready
    )
    timeout /t 1 /nobreak >nul
)
:cdpready
if "!READY!"=="0" (
    echo [警告] 15 秒内 CDP 端口仍未就绪，可能 Chrome 启动较慢或被对话框卡住。
    echo        请确认 Chrome 窗口已弹出，然后回到程序点「开始发送」。
) else (
    echo [OK] CDP 端口已就绪
)

echo.
if "%NEED_COPY%"=="1" (
    echo 下一步：
    echo   1. 在弹出的 Chrome 中确认 https://x.com 已登录（应该已是登录态）
    echo   2. 回到 outreach-hub，点「▶ 开始发送」或「▶ 开始搜索」，再点「已登录就绪」
    echo   本次登录会保存在 data\chrome_cdp_session\，下次无需重新登录
    echo.
    echo   日常 Chrome 改密码或登录新账号后，用 --refresh 重新同步
) else (
    echo 下一步：
    echo   1. 在弹出的 Chrome 中确认 https://x.com 已登录（隔离 profile 复用上次登录态）
    echo   2. 回到 outreach-hub，点「▶ 开始发送」或「▶ 开始搜索」，再点「已登录就绪」
    echo.
    echo   若 X 登录态失效，用 --refresh 从日常 Chrome 重新同步
)
echo.

REM ── 7. 启动 GUI（前台）──────────────────────────────────────────────────────
echo 启动 outreach-hub ...
uv run python main.py

echo.
echo 程序已退出。
pause
endlocal
exit /b 0


REM ════════════════════════════════════════════════════════════════════════════
REM 子程序：从日常 Chrome 拷贝 X 登录态到隔离 profile
REM ════════════════════════════════════════════════════════════════════════════
:do_copy
if not exist "%SRC_DIR%\Default" (
    echo [错误] 未找到日常 Chrome profile：%SRC_DIR%
    echo        请先在日常 Chrome 登录 https://x.com，完全退出 Chrome 后重跑。
    echo        或用 --no-system 纯空白启动（首次可能被 X 风控）。
    exit /b 1
)

REM 4a. 日常 Chrome 必须完全退出（cookies SQLite 写锁，否则拷出来损坏）
:waitchrome
tasklist /FI "IMAGENAME eq chrome.exe" /NH /FO CSV 2>nul | findstr /I "chrome.exe" >nul
if not errorlevel 1 (
    echo.
    echo [提示] 检测到 Chrome 正在运行。首次同步登录态需要完全退出 Chrome
    echo        （含任务栏托盘里后台进程），否则 cookies 被占用，拷出来会损坏。
    echo        请先完全退出 Chrome，然后按任意键继续检测...
    pause >nul
    goto :waitchrome
)

REM 4b. 选源 profile：--profile 指定 / 默认 Default（多 profile 时提示）
set "SRC_PROFILE=Default"
if not "%EXPLICIT_PROFILE%"=="" set "SRC_PROFILE=%EXPLICIT_PROFILE%"

if "%SRC_PROFILE%"=="Default" (
    set "MULTI=0"
    for /d %%D in ("%SRC_DIR%\Profile *") do set "MULTI=1"
    if "!MULTI!"=="1" (
        echo [提示] 检测到多个 Chrome profile，默认用 Default。
        echo        若 X 登在别的 profile（如 Profile 1），退出后用 --profile "Profile 1" 重跑。
    )
)

set "SRC=%SRC_DIR%\%SRC_PROFILE%"
set "DST=%USER_DATA%\Default"

if not exist "%SRC%\Network\Cookies" if not exist "%SRC%\Cookies" (
    echo [错误] 源 profile 没有 cookies：%SRC%
    echo        该 profile 可能没登录 X。请在日常 Chrome 登录 https://x.com 后重试，
    echo        或用 --profile 指定登录了 X 的那个 profile。
    exit /b 1
)

REM 4c. 拷贝全局 Local State（含 cookies 的 AES-GCM 解密 key，DPAPI 绑定当前 Windows
REM     用户，同用户下可正常解密，所以必须拷过来）
mkdir "%USER_DATA%" 2>nul
if exist "%SRC_DIR%\Local State" copy /Y "%SRC_DIR%\Local State" "%USER_DATA%\Local State" >nul

REM 4d. 拷贝 profile 文件：Network 子目录下的 cookies
mkdir "%DST%\Network" 2>nul
for %%F in ("Network\Cookies" "Network\Cookies-journal") do (
    if exist "%SRC%\%%~F" copy /Y "%SRC%\%%~F" "%DST%\%%~F" >nul
)
REM 4d'. profile 根的认证 / 状态文件
for %%F in ("Cookies" "Cookies-journal" "Preferences" "Secure Preferences" "Login Data" "Login Data-journal" "Web Data" "Web Data-journal" "History" "History-journal" "Favicons" "Favicons-journal" "Top Sites" "Top Sites-journal" "Bookmarks" "Visited Links") do (
    if exist "%SRC%\%%~F" copy /Y "%SRC%\%%~F" "%DST%\%%~F" >nul
)

REM 4e. 拷贝目录（robocopy /E 增量，不删除隔离 profile 自己产生的数据）
for %%D in ("Local Storage" "Session Storage" "IndexedDB") do (
    if exist "%SRC%\%%~D" robocopy "%SRC%\%%~D" "%DST%\%%~D" /E /NFL /NDL /NJH /NJS /NP >nul
)
if errorlevel 8 echo [警告] robocopy 部分目录同步异常（退出码 %errorlevel%），登录态可能不全。

REM 4f. 标记已初始化，以后启动直接复用，不再拷贝
echo initialized> "%INIT_FLAG%"
echo [OK] 已从「%SRC_PROFILE%」同步登录态到隔离 profile
echo [OK] 以后启动自动复用，无需再次同步（日常 Chrome 改密码/换号才用 --refresh）
exit /b 0


REM ════════════════════════════════════════════════════════════════════════════
:usage
echo 用法：start_chrome_cdp.bat [--refresh] [--no-system] [--profile NAME]
echo.
echo   （默认）           智能模式：隔离 profile 空白则自动同步日常 Chrome 登录态，
echo                     已有登录态则直接复用
echo   --refresh          强制重新拷贝（即使已初始化；改密码/换号后用一次）
echo   --no-system        不拷贝，纯空白 profile（调试/手登用，首次可能被 X 风控）
echo   --profile NAME     显式指定源 profile（如 Default / "Profile 1"）
echo   --system           向后兼容（默认即智能同步，加不加效果一样）
echo.
echo   首次自动同步需要日常 Chrome 完全退出（含任务栏托盘），否则 cookies 拷出来会损坏。
exit /b 0
