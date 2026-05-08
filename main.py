"""
Web3 Outreach Hub — 入口
"""
import sys
import os

# ── 多进程安全：必须在所有 multiprocessing 相关 import 之前执行 ────────────────
try:
    import multiprocessing
    multiprocessing.set_start_method("spawn", force=True)
except Exception:
    pass

# ── PyInstaller frozen 环境下，确保 gui/ 和 workers/ 可被 import ──────────────
# sys._MEIPASS = 临时解压目录（_internal/），os.path.dirname(sys.executable) = exe 所在目录
if getattr(sys, "frozen", False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, _APP_DIR)

import db
db.init_db()

from gui.app import App

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = App()
    app.mainloop()
