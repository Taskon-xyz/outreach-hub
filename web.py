"""
Web3 Outreach Hub — Web UI 入口
启动 FastAPI 服务器并打开浏览器
"""
import sys, os

# ── 路径 ──────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _APP_DIR)

import db
db.init_db()

if __name__ == "__main__":
    import webbrowser, threading, uvicorn
    from web_server import app  # noqa: F401

    port = 8765
    # 延迟 1.5 秒后打开浏览器
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    print(f"[OutreachHub Web] http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
