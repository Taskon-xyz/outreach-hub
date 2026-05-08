"""
TG Sender Worker — 发送 Telegram DM（WinRT OCR + PyAutoGUI 控制桌面 Telegram）
基于 TG_AUTO_DM.py

注意：此 worker 通过屏幕 OCR 操作桌面 Telegram 客户端，不直接调用 Telethon API。
      发送时需要在桌面登录对应的 TG 账号（即「⚙️ 设置」中「DM 发送账号」填写的那个号）。
      API ID / Hash 仅存档备用，不在此处调用。
      OCR 引擎使用 Windows 原生 WinRT OCR（zh-Hans-CN），速度快、准确率高。
"""
import time
import random
import asyncio
from datetime import datetime, timedelta

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
import config
from workers.base_worker import BaseWorker


def _run_async(coro):
    """在同步线程中运行异步函数"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


class TGSenderWorker(BaseWorker):
    def __init__(self, log_callback, progress_callback=None,
                 source="all", max_per_hour=None, message_name="", message_content=""):
        super().__init__(log_callback, progress_callback)
        # source: "all"（含 NULL 所有记录）| 任意用户自定义 tag | "tg_left"
        self.source          = source or "all"
        self.max_per_hour    = max_per_hour or config.TG_MAX_PER_HOUR
        self.message_name    = message_name
        self.message_content = message_content

    def _ocr_recognize(self, img):
        """用 WinRT OCR 识别图片，返回 [(text, x, y, w, h), ...]"""
        import winocr

        async def _recognize():
            return await winocr.recognize_pil(img, lang='zh-Hans-CN')

        result = _run_async(_recognize())
        words = []
        for line in result.lines:
            for w in line.words:
                r = w.bounding_rect
                words.append((w.text, r.x, r.y, r.width, r.height))
        return words, result.lines

    def _find_handle_in_ocr(self, words, target_name, region):
        """
        在 OCR 结果中查找 @username，返回点击坐标 (abs_x, abs_y) 或 None。
        WinRT OCR 能准确识别 @username，直接字符串匹配即可。
        """
        target_lower = target_name.lower()
        target_at = f"@{target_lower}"

        best_match = None
        for (text, x, y, w, h) in words:
            # 纯精确匹配 @username
            if text.lower() == target_at:
                best_match = (text, x, y, w, h)
                break

        if best_match:
            text, x, y, w, h = best_match
            abs_x = region["left"] + x + w / 2
            abs_y = region["top"] + y + h / 2
            return abs_x, abs_y, text
        return None

    def _check_send_blocked(self, lines):
        """检查 OCR 结果中是否包含发送限制关键词"""
        block_keywords = ["sorry", "mutual contact", "only send",
                          "can't write", "privacy settings"]
        for line in lines:
            text_lower = line.text.lower()
            for kw in block_keywords:
                if kw in text_lower:
                    return True, line.text
        return False, ""

    def run(self):
        try:
            import mss, winocr, pyautogui, pyperclip
            from PIL import Image
        except ImportError as e:
            self.log(f"缺少依赖：{e}，请运行 pip install winocr mss pyautogui pyperclip")
            return

        if not self.message_content:
            self.log("消息内容为空，请先在「文案」页配置激活文案")
            return

        self.log("WinRT OCR 就绪（Windows 原生引擎，无需初始化）")

        # 收集待发列表
        handles = self._collect_handles()
        if not handles:
            self.log("没有待发送的用户")
            return

        self.log(f"待发 {len(handles)} 个用户，每小时限额 {self.max_per_hour}")

        sent_this_hour = 0
        hour_start     = datetime.now()
        search_pos     = db.get_tg_search_pos()

        self.log("5 秒后开始，请切换到 Telegram 窗口...")
        for i in range(5, 0, -1):
            if self._stop:
                return
            self.log(f"  {i}...")
            time.sleep(1)

        for idx, username in enumerate(handles):
            if self._stop:
                self.log("已停止")
                break

            # 小时限额检查
            now = datetime.now()
            if now - hour_start > timedelta(hours=1):
                sent_this_hour = 0
                hour_start     = now
                self.log("新的一小时，重置计数器")

            if sent_this_hour >= self.max_per_hour:
                next_hour = hour_start + timedelta(hours=1)
                self.log(f"达到限额，等待至 {next_hour.strftime('%H:%M:%S')}...")
                while datetime.now() < next_hour:
                    if self._stop:
                        return
                    time.sleep(1)
                sent_this_hour = 0
                hour_start     = datetime.now()

            name = username.lstrip('@')
            self.log(f"[{idx+1}/{len(handles)}] 处理：{name}")

            # 点击搜索栏并输入
            pyautogui.click(search_pos[0], search_pos[1])
            time.sleep(0.3)
            pyautogui.hotkey('ctrl', 'a')
            pyautogui.press('backspace')
            pyperclip.copy(name)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(5)

            # WinRT OCR 校验
            found = False
            region = db.get_ocr_region()
            with mss.mss() as sct:
                sct_img = sct.grab(region)
                img = Image.frombytes("RGB", (sct_img.width, sct_img.height),
                                      sct_img.bgra, "raw", "BGRX")

            words, _ = self._ocr_recognize(img)
            match = self._find_handle_in_ocr(words, name, region)

            if match:
                abs_x, abs_y, matched_text = match
                pyautogui.click(abs_x, abs_y)
                found = True
                self.log(f"  OCR 匹配：{matched_text}")

            if found:
                time.sleep(5)
                pyperclip.copy(self.message_content)
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.8)
                pyautogui.press('enter')

                # 等待并检测是否弹出限制对话框
                time.sleep(5 + random.uniform(1, 2))

                check_region = db.get_send_check_region()
                with mss.mss() as sct:
                    sct_img = sct.grab(check_region)
                    img_check = Image.frombytes(
                        "RGB", (sct_img.width, sct_img.height),
                        sct_img.bgra, "raw", "BGRX")

                _, check_lines = self._ocr_recognize(img_check)
                send_blocked, blocked_reason = self._check_send_blocked(check_lines)

                pyautogui.press('esc')
                time.sleep(0.3)
                pyautogui.press('esc')

                if send_blocked:
                    self.log(f"  ✗ 账号受限，消息未发出：{blocked_reason}")
                    self.log("⚠️  检测到发送限制，脚本已自动暂停")
                    self._stop = True
                    break
                else:
                    sent_this_hour += 1
                    db.log_send(username, "telegram", self.source, self.message_name)
                    self.log(f"  ✓ 已发送（本小时 {sent_this_hour}/{self.max_per_hour}）")

                self.progress(idx + 1, len(handles))
            else:
                db.skip_handle(username, reason="ocr_no_match")
                self.log(f"  ✗ 未找到匹配，已标记跳过")
                pyautogui.press('esc')

        self.log("TG 发送完成！")

    def _collect_handles(self):
        return db.get_unsent_tg_by_source(self.source)
