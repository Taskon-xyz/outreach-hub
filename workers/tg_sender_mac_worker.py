"""
TG Sender Worker (macOS) — 发送 Telegram DM
使用 macOS Vision framework OCR + PyAutoGUI 控制桌面 Telegram

系统权限要求（首次使用需手动授权）：
  - 辅助功能：系统设置 → 隐私与安全性 → 辅助功能 → 勾选 Terminal / Python
  - 屏幕录制：系统设置 → 隐私与安全性 → 屏幕录制 → 勾选 Terminal / Python
"""
import time
import random
import subprocess
import tempfile
import os
from datetime import datetime, timedelta

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
import config
from workers.base_worker import BaseWorker


def _check_accessibility() -> bool:
    """检测辅助功能权限"""
    try:
        import Quartz
        return bool(Quartz.AXIsProcessTrusted())
    except Exception:
        return False


def _check_screen_recording() -> bool:
    """检测屏幕录制权限（截一张图，看是否全黑）"""
    try:
        import mss
        from PIL import Image
        with mss.mss() as sct:
            monitors = sct.monitors
            if len(monitors) < 2:
                return False
            region = {"top": 0, "left": 0, "width": 50, "height": 50,
                      "mon": 1}
            sct_img = sct.grab(region)
            img = Image.frombytes("RGB", (sct_img.width, sct_img.height),
                                  sct_img.bgra, "raw", "BGRX")
            pixels = list(img.getdata())
            # 全黑说明没有屏幕录制权限
            all_black = all(r < 5 and g < 5 and b < 5 for r, g, b in pixels)
            return not all_black
    except Exception:
        return False


def _open_accessibility_prefs():
    subprocess.Popen([
        "open",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    ])


def _open_screen_recording_prefs():
    subprocess.Popen([
        "open",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
    ])


def _ocr_pil_image(pil_image):
    """
    用 macOS Vision framework 识别图片文字。
    返回 [(text, x, y, w, h), ...] —— 像素坐标，原点在左上角。

    Vision 的 bounding box 是归一化坐标（0~1），原点在左下角，需转换。
    """
    import Vision
    from Foundation import NSURL

    img_w, img_h = pil_image.size

    # 写入临时 PNG，通过文件 URL 给 Vision 读取
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name
    try:
        pil_image.save(tmp_path, format="PNG")

        url = NSURL.fileURLWithPath_(tmp_path)
        request = Vision.VNRecognizeTextRequest.alloc().init()
        # Accurate 模式准确率高，Fast 模式速度快
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(False)

        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})
        success, error = handler.performRequests_error_([request], None)
        if not success:
            return [], []

        words = []
        lines_text = []
        for obs in (request.results() or []):
            candidates = obs.topCandidates_(1)
            if not candidates:
                continue
            text = str(candidates[0].string())
            lines_text.append(text)

            bbox = obs.boundingBox()
            # 归一化坐标 → 像素坐标（Vision Y 轴朝上，需翻转）
            px = bbox.origin.x * img_w
            py = (1.0 - bbox.origin.y - bbox.size.height) * img_h
            pw = bbox.size.width  * img_w
            ph = bbox.size.height * img_h
            words.append((text, px, py, pw, ph))

        return words, lines_text
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


class TGSenderMacWorker(BaseWorker):
    def __init__(self, log_callback, progress_callback=None,
                 source="all", max_per_hour=None,
                 message_name="", message_content=""):
        super().__init__(log_callback, progress_callback)
        self.source          = source or "all"
        self.max_per_hour    = max_per_hour or config.TG_MAX_PER_HOUR
        self.message_name    = message_name
        self.message_content = message_content

    # ── 权限检测 ─────────────────────────────────────────────────
    def _check_permissions(self) -> bool:
        ok = True

        if not _check_accessibility():
            self.log("❌ 缺少「辅助功能」权限，无法控制鼠标/键盘")
            self.log("   → 正在打开系统设置，请勾选 Terminal 或 Python 后重试")
            _open_accessibility_prefs()
            ok = False

        if not _check_screen_recording():
            self.log("❌ 缺少「屏幕录制」权限，截图将为全黑")
            self.log("   → 正在打开系统设置，请勾选 Terminal 或 Python 后重试")
            _open_screen_recording_prefs()
            ok = False

        return ok

    # ── OCR 相关 ─────────────────────────────────────────────────
    def _find_handle_in_ocr(self, words, target_name, region):
        """在 OCR 结果中精确匹配 @username，返回绝对像素坐标或 None"""
        target_at = f"@{target_name.lower()}"
        for (text, x, y, w, h) in words:
            if text.lower() == target_at:
                abs_x = region["left"] + x + w / 2
                abs_y = region["top"]  + y + h / 2
                return abs_x, abs_y, text
        return None

    def _check_send_blocked(self, lines_text):
        """检查 OCR 结果中是否包含发送限制关键词"""
        block_keywords = ["sorry", "mutual contact", "only send",
                          "can't write", "privacy settings"]
        for text in lines_text:
            tl = text.lower()
            for kw in block_keywords:
                if kw in tl:
                    return True, text
        return False, ""

    # ── 主流程 ───────────────────────────────────────────────────
    def run(self):
        try:
            import mss
            import pyautogui
            import pyperclip
            from PIL import Image
        except ImportError as e:
            self.log(f"缺少依赖：{e}")
            self.log("请运行：pip install mss pyautogui pyperclip Pillow pyobjc-framework-Vision")
            return

        try:
            import Vision  # noqa
        except ImportError:
            self.log("缺少 pyobjc-framework-Vision")
            self.log("请运行：pip install pyobjc-framework-Vision")
            return

        if not self.message_content:
            self.log("消息内容为空，请先在「文案」页配置激活文案")
            return

        if not self._check_permissions():
            self.log("请授权后重新启动脚本")
            return

        self.log("macOS Vision OCR 就绪")

        handles = db.get_unsent_tg_by_source(self.source)
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

            # 小时限额
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

            # 点击搜索栏并输入（macOS 用 Cmd 而非 Ctrl）
            pyautogui.click(search_pos[0], search_pos[1])
            time.sleep(0.3)
            pyautogui.hotkey('command', 'a')
            pyautogui.press('backspace')
            pyperclip.copy(name)
            pyautogui.hotkey('command', 'v')
            time.sleep(5)

            # OCR 识别
            region = db.get_ocr_region()
            with mss.mss() as sct:
                sct_img = sct.grab(region)
                img = Image.frombytes("RGB", (sct_img.width, sct_img.height),
                                      sct_img.bgra, "raw", "BGRX")

            words, _ = _ocr_pil_image(img)
            match = self._find_handle_in_ocr(words, name, region)

            if match:
                abs_x, abs_y, matched_text = match
                pyautogui.click(abs_x, abs_y)
                self.log(f"  OCR 匹配：{matched_text}")
                time.sleep(5)

                pyperclip.copy(self.message_content)
                pyautogui.hotkey('command', 'v')
                time.sleep(0.8)
                pyautogui.press('return')

                time.sleep(5 + random.uniform(1, 2))

                # 检查是否被限制
                check_region = db.get_send_check_region()
                with mss.mss() as sct:
                    sct_img = sct.grab(check_region)
                    img_check = Image.frombytes(
                        "RGB", (sct_img.width, sct_img.height),
                        sct_img.bgra, "raw", "BGRX")

                _, check_lines = _ocr_pil_image(img_check)
                send_blocked, blocked_reason = self._check_send_blocked(check_lines)

                pyautogui.press('escape')
                time.sleep(0.3)
                pyautogui.press('escape')

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
                pyautogui.press('escape')

        self.log("TG 发送完成！")
