# build.ps1 — Build Web3 Outreach Hub .exe
# 用法: powershell -ExecutionPolicy Bypass -File build.ps1

$ErrorActionPreference = "Stop"
$PROJECT = Split-Path -Parent $MyInvocation.MyCommand.Path

function Get-CdpErrors($log) {
    # placeholder for CDP error collection (used by playwright test introspection)
    $errors = @()
    return $errors
}

Write-Host "════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Outreach Hub Build Script" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── 前置检查 ────────────────────────────────────────────────────────────────
Write-Host "[1/4] 检查依赖..." -ForegroundColor Yellow

$pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
if (-not $pyinstaller) {
    Write-Host "  PyInstaller 未安装，正在安装..." -ForegroundColor Yellow
    pip install pyinstaller
}

# ── 安装 Playwright 浏览器 ───────────────────────────────────────────────────
Write-Host "[2/4] 安装 Playwright 浏览器..." -ForegroundColor Yellow
python -m playwright install chromium --with-deps 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  playwright install 失败，尝试备用安装..." -ForegroundColor Yellow
    python -m playwright install chromium 2>&1 | Out-Null
}

# ── 清理旧构建 ─────────────────────────────────────────────────────────────
Write-Host "[3/4] 清理旧构建..." -ForegroundColor Yellow
$buildDirs = @(
    "$PROJECT\dist\OutreachHub",
    "$PROJECT\dist\OutreachHub.exe",
    "$PROJECT\build"
)
foreach ($d in $buildDirs) {
    if (Test-Path $d) {
        Remove-Item -Path $d -Recurse -Force
        Write-Host "  已删除: $d" -ForegroundColor Gray
    }
}

# ── 运行 PyInstaller ────────────────────────────────────────────────────────
Write-Host "[4/4] 运行 PyInstaller（这可能需要 3-10 分钟）..." -ForegroundColor Yellow
Write-Host ""

Push-Location $PROJECT
try {
    pyinstaller outreach-hub.spec --clean --noconfirm 2>&1 | Tee-Object -Variable buildLog
} finally {
    Pop-Location
}

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "PyInstaller 构建失败，常见问题：".ForegroundColor Red
    Write-Host "  1. 如果 easyocr / torch 报错：将它们加入 hiddenimports".ForegroundColor Red
    Write-Host "  2. 如果 dll 缺失：在 build\OutreachHub\_internal\ 下检查".ForegroundColor Red
    Write-Host "  3. 如果找不到 main.py：检查 spec 中 pathex 是否正确".ForegroundColor Red
    exit 1
}

# ── 验证结果 ────────────────────────────────────────────────────────────────
$exePath = "$PROJECT\dist\OutreachHub\OutreachHub.exe"
if (Test-Path $exePath) {
    $sizeMB = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
    Write-Host ""
    Write-Host "════════════════════════════════════════" -ForegroundColor Green
    Write-Host "  构建成功！" -ForegroundColor Green
    Write-Host "  路径: $exePath" -ForegroundColor Green
    Write-Host "  主文件大小: ${sizeMB} MB" -ForegroundColor Green
    Write-Host "  内含完整运行时和所有依赖" -ForegroundColor Green
    Write-Host ""
    Write-Host "首次运行注意：".ForegroundColor Yellow
    Write-Host "  1. 请把 outreach.db 和 credentials.json 放到 exe 同目录的 data\ 下" -ForegroundColor Yellow
    Write-Host "  2. 运行时如有 DLL 报错，把相关 .dll 复制到 exe 同目录" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "可双击 exe 直接运行（无需安装 Python）".ForegroundColor Green
    Write-Host "════════════════════════════════════════" -ForegroundColor Green
} else {
    Write-Host "构建完成但找不到 exe，检查 dist 目录" -ForegroundColor Red
}
