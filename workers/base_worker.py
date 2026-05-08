"""
Worker 基类
"""


class BaseWorker:
    def __init__(self, log_callback, progress_callback=None):
        self.log = log_callback
        self.progress = progress_callback or (lambda cur, total: None)
        self._stop = False

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

    def run(self):
        raise NotImplementedError
