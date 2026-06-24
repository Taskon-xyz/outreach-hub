@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ══ Outreach Hub — Windows 版 Chrome CDP 启动（X 发送专用）══════════════════
REM
REM 启动一个监听 9222 的真实 Chrome（项目本地隔离 profile），在其中登录 X。
REM 登录态保存在 data\chrome_cdp_session\，下次无需重新登录。
REM
REM X 发送（Playwright）通过 CDP 连接这个 Chrome 来自动发 DM。
REM Telegram 发送走 web.telegram.org，无需本脚本。
REM
REM 用法：双击运行，或在 PowerShell/CMD 里执行 scripts\start_chrome_cdp.bat

cd /d "%~dp0\.."

set PORT=9222
set USER_DATA=%cd%\data\chrome_cdp_session

REM ── 1. 定位 Chrome ──────────────────────────────────────────────────────────
set CHROME=
for %%P in (
    "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
    "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
    "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
) do (
    if exist "%%~P" set CHROME=%%~P
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

REM ── 3. 启动 Chrome CDP（后台新窗口）────────────────────────────────────────
echo 启动 Chrome CDP（端口 %PORT%）...
if not exist "data" mkdir "data"
start "" "%CHROME%" ^
    --remote-debugging-port=%PORT% ^
    --remote-debugging-address=127.0.0.1 ^
    --user-data-dir="%USER_DATA%" ^
    --no-first-run ^
    --no-default-browser-check

REM ── 4. 等待 CDP 端口就绪（最多 ~15 秒）──────────────────────────────────────
echo 等待 CDP 端口就绪...
set READY=0
for /l %%i in (1,1,30) do (
    powershell -NoProfile -Command "try{(Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 'http://127.0.0.1:9222/json/version')|Out-Null; exit 0}catch{exit 1}" >nul 2>&1
    if !errorlevel!==0 (
        set READY=1
        goto :ready
    )
    timeout /t 1 /nobreak >nul
)
:ready
if "!READY!"=="0" (
    echo [警告] 15 秒内 CDP 端口仍未就绪，可能 Chrome 启动较慢或被对话框卡住。
    echo        请确认 Chrome 窗口已弹出，然后回到程序点「开始发送」。
) else (
    echo [OK] CDP 端口已就绪
)

echo.
echo 下一步：
echo   1. 在弹出的 Chrome 中打开 https://x.com 并登录
echo   2. 登录成功后回到 outreach-hub 程序
echo   3. 点击「▶ 开始发送」，再点「已登录就绪」
echo   本次登录会保存在 data\chrome_cdp_session\，下次无需重新登录
echo.

REM ── 5. 启动 GUI（前台）──────────────────────────────────────────────────────
echo 启动 outreach-hub ...
uv run python main.py

echo.
echo 程序已退出。
pause
endlocal
