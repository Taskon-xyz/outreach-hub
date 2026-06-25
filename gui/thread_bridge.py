"""
线程安全桥：后台线程通过 enqueue(fn) 把 UI 任务推入队列，
主线程在 after(50) 轮询中统一执行，避免任何跨线程调用 Tkapp_Call。

call_on_main(fn) 供需要“拿到返回值”的场景（如弹框）使用：后台线程调用时
把 fn marshal 到主线程执行并阻塞取结果；命令行 / 已在主线程时直接执行。
"""
import queue as _q
import threading as _t

_ui_queue: _q.Queue = _q.Queue()
_drain_running = False   # drain() 是否已在主线程启动轮询


def enqueue(fn) -> None:
    """线程安全：将 fn 推入 UI 主线程执行队列（可在任意线程调用）。"""
    _ui_queue.put_nowait(fn)


def drain(root) -> None:
    """必须在主线程调用。排干当前队列，然后重新调度自身。"""
    global _drain_running
    _drain_running = True
    try:
        while True:
            fn = _ui_queue.get_nowait()
            try:
                fn()
            except Exception:
                import traceback
                traceback.print_exc()
    except _q.Empty:
        pass
    root.after(50, drain, root)


def call_on_main(fn, timeout=600):
    """
    在主线程执行 fn 并返回其结果（供弹框等需要返回值的 GUI 操作使用）。

    - 当前已是主线程（命令行 / 非 GUI 场景）：直接执行 fn 返回。
    - 后台线程 + GUI 已启动 drain 轮询：把 fn 推入队列，阻塞等待主线程
      执行完毕后返回结果（fn 抛异常则在此原样重抛）。
    - 后台线程 + GUI 未启动 drain：直接抛 RuntimeError，避免死等。

    ⚠️ Tk 窗口 / 输入框只能在主线程创建与操作；任何弹框都必须经由本函数，
    否则在后台线程触发会崩溃（macOS：NSWindow should only be instantiated
    on the main thread）或静默返回 None（Windows，被当成“用户取消”）。
    """
    if _t.current_thread() is _t.main_thread():
        return fn()

    if not _drain_running:
        raise RuntimeError("主线程 UI 轮询未启动，无法在主线程执行弹框")

    box = {}
    done = _t.Event()

    def _wrapped():
        try:
            box["v"] = fn()
        except BaseException as e:   # 需原样回传给调用线程
            box["e"] = e
        finally:
            done.set()

    _ui_queue.put_nowait(_wrapped)
    if not done.wait(timeout):
        raise TimeoutError(f"主线程执行超时（{timeout}s）")
    if "e" in box:
        raise box["e"]
    return box.get("v")
