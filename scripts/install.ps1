# Outreach Hub Windows 一键安装脚本
#
# 适用：全新 Windows 10/11 设备，不需要预装任何开发工具
#
# 使用方式 — 复制粘贴到 PowerShell 运行：
#   Set-ExecutionPolicy Bypass -Scope Process -Force
#   $s = Invoke-RestMethod https://raw.githubusercontent.com/Taskon-xyz/outreach-hub/main/scripts/install.ps1; Invoke-Expression $s
#
# 或 clone 后运行：
#   git clone https://github.com/Taskon-xyz/outreach-hub.git
#   cd outreach-hub
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1

$ErrorActionPreference = "Stop"

# ══ 前置：TLS 1.2（Windows PowerShell 5.1 默认只用 TLS 1.0，GitHub/CDN 会拒绝） ══
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$REPO_URL = "https://github.com/Taskon-xyz/outreach-hub.git"
$REPO_NAME = "outreach-hub"

Write-Host ""
Write-Host "Outreach Hub 安装 (Windows)" -ForegroundColor Cyan
Write-Host "============================"

# ── 1. Git ────────────────────────────────────────────────────────────────────
if (Get-Command git -ErrorAction SilentlyContinue) {
    Write-Host "[OK] Git $(git --version)" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "安装 Git..." -ForegroundColor Yellow

    # 优先用 winget（Windows 11 自带，Windows 10 较新版本也有）
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "  使用 winget 安装 Git for Windows..."
        winget install --id Git.Git --source winget --accept-package-agreements --accept-source-agreements
    } else {
        # 没有 winget：下载安装包
        Write-Host "  下载 Git for Windows 安装包..."
        $gitInstaller = "$env:TEMP\GitSetup.exe"
        # 使用官方重定向 URL，自动获取最新 64-bit 版本
        Invoke-WebRequest -Uri "https://github.com/git-for-windows/git/releases/latest/download/Git-2.50.0-64-bit.exe" -OutFile $gitInstaller -UseBasicParsing
        Write-Host "  启动安装向导（请一路 Next 完成安装）..."
        Start-Process -FilePath $gitInstaller -Wait
    }

    # 刷新 PATH（Git 安装后写入 Program Files 或 Program Files (x86)）
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        # 手动补上常见 Git 路径
        $gitDir = "${env:ProgramFiles}\Git\cmd"
        if (Test-Path $gitDir) { $env:Path = "$gitDir;$($env:Path)" }
        $gitDir = "${env:ProgramFiles(x86)}\Git\cmd"
        if (Test-Path $gitDir) { $env:Path = "$gitDir;$($env:Path)" }
    }

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "[错误] Git 安装后仍未找到。请重启终端后重新运行此脚本。" -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] Git $(git --version)" -ForegroundColor Green
}

# ── 2. 确认代码目录 ──────────────────────────────────────────────────────────
if ((Test-Path "pyproject.toml") -and ((Get-Content "pyproject.toml" -Raw) -match "outreach-hub")) {
    $REPO_DIR = (Get-Location).Path
    Write-Host "[OK] 已在项目目录: $REPO_DIR" -ForegroundColor Green
} else {
    if (Test-Path $REPO_NAME) {
        Write-Host "[OK] 目录 $REPO_NAME 已存在，拉取最新..." -ForegroundColor Green
        Set-Location $REPO_NAME
        git remote set-url origin $REPO_URL
        git pull
    } else {
        Write-Host "克隆仓库..."
        git clone $REPO_URL
        Set-Location $REPO_NAME
    }
    $REPO_DIR = (Get-Location).Path
}

# ── 3. Google Chrome ──────────────────────────────────────────────────────────
$chromePaths = @(
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "${env:LOCALAPPDATA}\Google\Chrome\Application\chrome.exe"
)
$chromeFound = $false
foreach ($p in $chromePaths) {
    if (Test-Path $p) { $chromeFound = $true; break }
}

if ($chromeFound) {
    Write-Host "[OK] Google Chrome" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "安装 Google Chrome..." -ForegroundColor Yellow

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "  使用 winget 安装 Chrome..."
        winget install --id Google.Chrome --source winget --accept-package-agreements --accept-source-agreements
    } else {
        $chromeInstaller = "$env:TEMP\ChromeSetup.exe"
        Write-Host "  下载 Chrome 安装程序..."
        Invoke-WebRequest -Uri "https://dl.google.com/chrome/win64/1.0.0.0/chrome_installer.exe" -OutFile $chromeInstaller -UseBasicParsing
        Write-Host "  启动安装（请等待自动完成）..."
        Start-Process -FilePath $chromeInstaller -Wait
    }

    # 再次检查
    $chromeFound = $false
    foreach ($p in $chromePaths) {
        if (Test-Path $p) { $chromeFound = $true; break }
    }
    if (-not $chromeFound) {
        Write-Host "[错误] Chrome 安装未完成。请手动安装后重试: https://www.google.com/chrome/" -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] Google Chrome" -ForegroundColor Green
}

# ── 4. uv 包管理器 ───────────────────────────────────────────────────────────
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "[OK] uv $(uv --version)" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "安装 uv 包管理器..." -ForegroundColor Yellow

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "  使用 winget 安装 uv..."
        # --source winget：msstore 源常因证书问题(0x8a15005e)失败并触发多源歧义，
        # 明确指定 winget 源，避免 winget 停下要求手动选择源而实际未安装。
        winget install --id astral-sh.uv --source winget --accept-package-agreements --accept-source-agreements
    }

    # 刷新 PATH
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"

    # winget 可能仍失败（证书/网络/源），fallback 到 uv 官方安装脚本
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "  winget 未成功，改用 uv 官方安装脚本..." -ForegroundColor Yellow
        $uvInstaller = "$env:TEMP\uv_install.ps1"
        Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -OutFile $uvInstaller -UseBasicParsing
        powershell -ExecutionPolicy Bypass -File $uvInstaller
        # 官方脚本装完后再次刷新 PATH
        $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
        $env:Path = "$machinePath;$userPath"
    }

    # uv 常见安装路径
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        $uvCandidates = @(
            "$env:USERPROFILE\.local\bin",
            "$env:LOCALAPPDATA\uv",
            "${env:ProgramFiles}\uv"
        )
        foreach ($dir in $uvCandidates) {
            if (Test-Path (Join-Path $dir "uv.exe")) {
                $env:Path = "$dir;$($env:Path)"
                break
            }
        }
    }

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "[错误] uv 安装后仍未找到。请重启终端后重新运行此脚本。" -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] uv $(uv --version)" -ForegroundColor Green
}

# ── 5. Python 依赖 + Playwright ──────────────────────────────────────────────
Write-Host ""
Write-Host "── 1/3 安装 Python 依赖 ────────────────────────────"
uv sync

Write-Host ""
Write-Host "── 2/3 安装 Playwright 浏览器 ──────────────────────"
uv run playwright install chromium

Write-Host ""
Write-Host "── 3/3 验证环境 ────────────────────────────────────"
uv run python -c "import tkinter; print('[OK] tkinter')"
uv run python -c "import customtkinter; print('[OK] customtkinter')"
uv run python -c "import playwright; print('[OK] playwright')"

# ── 6. 创建启动快捷脚本 ──────────────────────────────────────────────────────
$launcher = Join-Path $REPO_DIR "start.bat"
@"
@echo off
chcp 65001 >nul
cd /d "$REPO_DIR"
REM 一键启动：CDP Chrome（X 发送用）+ GUI（TG/X 均走 Playwright）
scripts\start_chrome_cdp.bat
"@ | Set-Content -Path $launcher -Encoding ASCII

# ── 7. 桌面快捷方式（指向 start_chrome_cdp.bat，一键启动）──────────────────
$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "Outreach Hub.lnk"
try {
    $wsh = New-Object -ComObject WScript.Shell
    $sc  = $wsh.CreateShortcut($lnkPath)
    $sc.TargetPath       = Join-Path $REPO_DIR "scripts\start_chrome_cdp.bat"
    $sc.WorkingDirectory = $REPO_DIR
    $sc.Description      = "启动 Outreach Hub（CDP Chrome + 桌面 GUI）"
    # 用 Chrome 图标，比默认 .bat 图标美观
    $chromeExe = @(
        "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "${env:LOCALAPPDATA}\Google\Chrome\Application\chrome.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($chromeExe) { $sc.IconLocation = "$chromeExe,0" }
    $sc.Save()
    Write-Host "[OK] 桌面快捷方式：$lnkPath" -ForegroundColor Green
} catch {
    Write-Host "[警告] 桌面快捷方式创建失败：$($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "       可手动右键 scripts\start_chrome_cdp.bat → 发送到 → 桌面快捷方式" -ForegroundColor Gray
}

# ── 完成 ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================" -ForegroundColor Cyan
Write-Host "安装完成！" -ForegroundColor Green
Write-Host ""
Write-Host "日常使用："
Write-Host "  双击桌面的「Outreach Hub」快捷方式 → 一键启动 CDP Chrome + 桌面 GUI"
Write-Host ""
Write-Host "首次使用："
Write-Host "  1. 双击 start.bat 启动（自动打开 CDP Chrome + GUI；TG/X 发送均走 Playwright）"
Write-Host "  2. Telegram 发送：在「发送」页点开始，自动打开 Telegram Web，登录后点「已登录就绪」"
Write-Host "  3. X 发送：start.bat 已打开 CDP Chrome，在其中登录 https://x.com，回程序点「已登录就绪」"
Write-Host "  4. 在设置页配置 Telegram 账号（解析功能需要）"
Write-Host ""
