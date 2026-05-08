#!/usr/bin/env bash
# 一次性环境准备：Python 依赖 + Playwright 浏览器
# 新机器只需运行一次，之后直接用 start_chrome_cdp.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "── 1/3 安装 Python 依赖 ────────────────────────────────"
uv sync

echo ""
echo "── 2/3 安装 Playwright 浏览器 ───────────────────────────"
uv run playwright install chromium

echo ""
echo "── 3/3 验证环境 ────────────────────────────────────────"
uv run python -c "import tkinter; print('✓ tkinter')"
uv run python -c "import customtkinter; print('✓ customtkinter')"
uv run python -c "import playwright; print('✓ playwright')"

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  环境准备完成！"
echo "  日常启动：./scripts/start_chrome_cdp.sh"
echo "══════════════════════════════════════════════════════════"
