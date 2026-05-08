#!/usr/bin/env bash
# 安装 Playwright 浏览器引擎（Chromium + Firefox）
set -euo pipefail
cd "$(dirname "$0")/.."
uv run playwright install chromium firefox
echo "✓ Playwright 浏览器安装完成"
