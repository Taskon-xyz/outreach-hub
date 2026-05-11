"""
线程安全桥：后台线程通过 enqueue(fn) 把 UI 任务推入队列，
主线程在 after(50) 轮询中统一执行，避免任何跨线程调用 Tkapp_Call。
"""
import queue as _q

_ui_queue: _q.Queue = _q.Queue()


def enqueue(fn) -> None:
    """线程安全：将 fn 推入 UI 主线程执行队列（可在任意线程调用）。"""
    _ui_queue.put_nowait(fn)


def drain(root) -> None:
    """必须在主线程调用。排干当前队列，然后重新调度自身。"""
    try:
        while True:
            _ui_queue.get_nowait()()
    except _q.Empty:
        pass
    root.after(50, drain, root)
