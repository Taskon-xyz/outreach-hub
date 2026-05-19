"""
Worker 基类
"""


class BaseWorker:
    def __init__(self, log_callback, progress_callback=None):
        self.log = log_callback
        self.progress = progress_callback or (lambda cur, total: None)
        self._stop   = False
        self._paused = False

    def safe_log(self, msg):
        """编码安全的日志输出，防止 GBK 环境下特殊字符崩溃"""
        try:
            self.log(msg)
        except (UnicodeEncodeError, UnicodeDecodeError, OSError):
            try:
                safe = msg.encode('ascii', errors='replace').decode('ascii')
                self.log(safe)
            except Exception:
                pass

    def stop(self):
        self._stop = True

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    async def _wait_if_paused(self):
        """在 async worker 的循环里调用：暂停时阻塞，恢复后继续。"""
        if not self._paused:
            return
        import asyncio
        self.log("⏸  已暂停，点击「▶ 恢复」继续...")
        while self._paused and not self._stop:
            await asyncio.sleep(0.5)
        if not self._stop:
            self.log("▶  已恢复")

    def run(self):
        raise NotImplementedError
