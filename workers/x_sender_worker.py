"""
X (Twitter) Sender Worker — 发送 Twitter DM（坐标自动化）
基于 xdm/app.py 的 _send_dm 逻辑
"""
import time
import random

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
import config
from workers.base_worker import BaseWorker


class XSenderWorker(BaseWorker):
    def __init__(self, log_callback, progress_callback=None,
                 message_name="", message_content="", source=None,
                 mode="x_links", role=None):
        super().__init__(log_callback, progress_callback)
        self.message_name    = message_name
        self.message_content = message_content
        self.source          = source
        self.mode            = mode
        self.role            = role

    def run(self):
        try:
            import pyautogui, pyperclip
        except ImportError as e:
            self.log(f"缺少依赖：{e}")
            return

        # 读取坐标
        try:
            dm_x, dm_y = map(int, open(config.DM_POS_FILE).read().strip().split(','))
            chat_x, chat_y = map(int, open(config.CHAT_POS_FILE).read().strip().split(','))
        except Exception:
            self.log("未找到坐标文件，请先在「发送」页完成坐标校准")
            return

        if not self.message_content:
            self.log("消息内容为空，请先在「文案」页配置激活文案")
            return

        if self.mode == "x_contacts":
            handles = db.get_unsent_x_contacts(role=self.role)
            role_label = self.role or "全部角色"
            if not handles:
                self.log(f"没有待发送的 X 关键人（{role_label}）")
                return
            self.log(f"待发 {len(handles)} 个关键人（{role_label}）")
        else:
            handles = db.get_unsent_x_handles(source=self.source)
            if not handles:
                src_label = {"cb_excel": "仓库导入", "cb_discover": "融资项目（CB Discover）",
                             "rootdata": "融资项目（RootData）", "chainscope": "链上变化",
                             "tokenfinder": "低交易量", "campaign": "活动举办"}.get(self.source, "全部")
                self.log(f"没有待发送的 X 用户（{src_label}）")
                return
            self.log(f"待发 {len(handles)} 个 X 用户")
        self.log("5 秒后开始，请切换到 Chrome（Twitter）...")
        for i in range(5, 0, -1):
            if self._stop:
                return
            self.log(f"  {i}...")
            time.sleep(1)

        for idx, handle in enumerate(handles):
            if self._stop:
                self.log("已停止")
                break

            self.log(f"[{idx+1}/{len(handles)}] {handle}")
            success = self._send_dm(
                handle, self.message_content,
                dm_x, dm_y, chat_x, chat_y,
                pyautogui, pyperclip
            )

            if success:
                src_tag = (
                    f"x_contacts:{self.role or 'all'}"
                    if self.mode == "x_contacts"
                    else (self.source or "x_link")
                )
                db.log_send(handle, "twitter", src_tag, self.message_name)
                self.log(f"  ✓ 已发送")
            else:
                self.log(f"  ✗ 发送失败，跳过")

            self.progress(idx + 1, len(handles))
            wait = random.uniform(5, 10)
            self.log(f"  等待 {wait:.1f} 秒...")
            time.sleep(wait)

        self.log("X 发送完成！")

    def _send_dm(self, handle, message, dm_x, dm_y, chat_x, chat_y, pyautogui, pyperclip):
        try:
            if handle.startswith('http'):
                url = handle
            else:
                url = f"https://x.com/{handle.lstrip('@')}"
            self.log(f"  打开主页：{url}")
            pyautogui.hotkey('ctrl', 'l')
            time.sleep(0.4)
            pyperclip.copy(url)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.3)
            pyautogui.press('enter')

            wait = 5 + random.uniform(1, 2)
            self.log(f"  等待页面加载 {wait:.1f}s...")
            time.sleep(wait)

            self.log(f"  点击 DM 按钮 ({dm_x},{dm_y})")
            pyautogui.click(dm_x, dm_y)
            time.sleep(5 + random.uniform(1, 2))

            self.log(f"  点击输入框 ({chat_x},{chat_y})")
            pyautogui.click(chat_x, chat_y)
            time.sleep(1 + random.uniform(0.5, 1))

            pyperclip.copy(message)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(1 + random.uniform(0.5, 1))
            pyautogui.press('enter')
            time.sleep(2 + random.uniform(0.5, 1))
            return True
        except Exception as e:
            self.log(f"  发送异常：{e}")
            return False
