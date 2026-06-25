"""
Telethon GUI 登录辅助
在 GUI 环境下用弹窗完成 手机号 → 验证码 → 2FA密码 登录流程。
session 有效时静默跳过，不弹窗。
"""
import asyncio
from tkinter import simpledialog


def _dialog(title, prompt, show_password=False):
    """
    弹出一个输入框，返回用户输入或 None（取消）。

    ⚠️ Tk 窗口只能在主线程创建与操作。本函数会自动把实际弹框动作 marshal
    到主线程执行——无论调用方处于主线程还是后台线程都安全。这正是修复
    “后台线程里点登录验证 → 看不到弹框 → 登录失败或已取消”的根因：
    旧实现在后台线程直接 tk.Tk() 建窗，macOS 崩溃（NSWindow must be on
    main thread）、Windows 静默返回 None 被当成“用户取消”。
    """
    def _impl():
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        try:
            return simpledialog.askstring(
                title, prompt, parent=root, show="*" if show_password else None)
        finally:
            root.destroy()

    try:
        from gui.thread_bridge import call_on_main
    except Exception:
        return _impl()   # 无 gui 包（纯命令行环境），回退直接执行
    return call_on_main(_impl)


async def async_start_client(client, log_callback=None):
    """
    对已有的 TelegramClient 执行 start，缺失凭证时弹 GUI 窗口。
    不会创建额外 client，成功后 client 保持连接状态供后续使用。

    Args:
        client: 已创建的 TelegramClient 实例
        log_callback: 日志回调

    Returns:
        True 登录成功，False 用户取消或失败（client 已断开）
    """
    def log(msg):
        if log_callback:
            log_callback(msg)

    await client.connect()

    if await client.is_user_authorized():
        log("会话有效，已登录")
        return True

    log("需要登录，请输入手机号...")
    phone = _dialog("Telegram 登录 - 手机号",
                    "请输入手机号（含国家区号）：\n示例：+8613800138000")
    if not phone:
        log("用户取消登录")
        await client.disconnect()
        return False

    await client.send_code_request(phone)
    log("验证码已发送")

    code = _dialog("Telegram 登录 - 验证码",
                   "请输入 Telegram 发送的验证码：")
    if not code:
        log("用户取消登录")
        await client.disconnect()
        return False

    try:
        await client.sign_in(phone, code)
    except Exception as e:
        if "password" in str(e).lower() or "2fa" in str(e).lower():
            password = _dialog("Telegram 登录 - 两步验证",
                               "请输入两步验证密码：", show_password=True)
            if not password:
                log("用户取消登录")
                await client.disconnect()
                return False
            await client.sign_in(password=password)
        else:
            log(f"登录失败：{e}")
            await client.disconnect()
            return False

    me = await client.get_me()
    log(f"登录成功：{me.first_name} (@{me.username or '无'})")
    return True


def login_telethon(purpose, log_callback=None):
    """
    用 GUI 弹窗完成 Telethon 登录。

    Args:
        purpose: 'parser' | 'left' | 'sender'
        log_callback: 日志回调

    Returns:
        成功返回 first_name (str)，用户取消返回 None，失败返回 None
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import db
    from telethon import TelegramClient

    def log(msg):
        if log_callback:
            log_callback(msg)

    api_id, api_hash, session = db.get_tg_credentials(purpose)
    if not api_id or not api_hash:
        log(f"❌ 未配置 Telegram API（{purpose}）。请到「⚙️ 设置」→「TG 账号凭证」填入 api_id / api_hash")
        log("   申请地址：https://my.telegram.org → API development tools")
        return None
    client = TelegramClient(session, api_id, api_hash)

    async def _login():
        await client.connect()

        if await client.is_user_authorized():
            me = await client.get_me()
            log(f"会话有效，已登录为：{me.first_name} (@{me.username or '无'})")
            await client.disconnect()
            return me.first_name

        log("需要登录，请输入手机号...")
        phone = _dialog("Telegram 登录 - 手机号",
                        "请输入手机号（含国家区号）：\n示例：+8613800138000")
        if not phone:
            log("用户取消登录")
            await client.disconnect()
            return None

        await client.send_code_request(phone)
        log(f"验证码已发送至 {phone}")

        code = _dialog("Telegram 登录 - 验证码",
                       "请输入 Telegram 发送的验证码：")
        if not code:
            log("用户取消登录")
            await client.disconnect()
            return None

        try:
            await client.sign_in(phone, code)
        except Exception as e:
            if "password" in str(e).lower() or "2fa" in str(e).lower():
                password = _dialog("Telegram 登录 - 两步验证",
                                   "此账号开启了两步验证，请输入密码：",
                                   show_password=True)
                if not password:
                    log("用户取消登录")
                    await client.disconnect()
                    return None
                await client.sign_in(password=password)
            else:
                log(f"登录失败：{e}")
                await client.disconnect()
                return None

        me = await client.get_me()
        log(f"登录成功：{me.first_name} (@{me.username or '无'})")
        await client.disconnect()
        return me.first_name

    try:
        return asyncio.run(_login())
    except Exception as e:
        log(f"登录异常：{e}")
        return None
