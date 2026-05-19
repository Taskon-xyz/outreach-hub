"""
浏览器反检测辅助（兼容层）

此模块的所有常量现在从 workers.browser_fingerprint 转发，保留旧名字
（STEALTH_ARGS / IGNORE_DEFAULT_ARGS / STEALTH_INIT_SCRIPT）以避免改动所有 worker。

新代码请直接 import workers.browser_fingerprint，可以拿到完整 PROFILE、
CONTEXT_KWARGS（new_context 一键配置）、EXTRA_HTTP_HEADERS（Sec-CH-UA-* 头）。
"""
from workers.browser_fingerprint import (
    BROWSER_ARGS as STEALTH_ARGS,
    IGNORE_DEFAULT_ARGS,
    INIT_SCRIPT as STEALTH_INIT_SCRIPT,
    CONTEXT_KWARGS,
    EXTRA_HTTP_HEADERS,
    PROFILE,
)

__all__ = [
    "STEALTH_ARGS",
    "IGNORE_DEFAULT_ARGS",
    "STEALTH_INIT_SCRIPT",
    "CONTEXT_KWARGS",
    "EXTRA_HTTP_HEADERS",
    "PROFILE",
]
