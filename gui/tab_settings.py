"""
设置标签页 — DM 冷却 + 三个 TG 账号凭证 + 坐标校准
"""
import threading
import time
import tkinter.ttk as ttk
import customtkinter as ctk
from tkinter import messagebox, Canvas
import os

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
import config


class SettingsTab:
    def __init__(self, parent):
        self.parent = parent
        self._build()
        self._load_all()

    # ════════════════ 整体布局（Canvas 滚动，性能优于 CTkScrollableFrame） ══
    def _build(self):
        # Canvas + Scrollbar（而不是 CTkScrollableFrame）
        container = ctk.CTkFrame(self.parent, fg_color="transparent")
        container.pack(fill="both", expand=True)

        v_scroll = ttk.Scrollbar(container, orient="vertical")
        v_scroll.pack(side="right", fill="y")

        # 取当前外观模式对应的背景色，防止 cget 失败
        bg_color = self.parent.cget("fg_color")
        self._canvas = Canvas(
            container, borderwidth=0, bg=bg_color,
            highlightthickness=0,
            yscrollcommand=v_scroll.set,
        )
        self._canvas.pack(side="left", fill="both", expand=True)
        v_scroll.configure(command=self._canvas.yview)

        # 实际盛放内容的 frame，动态高度随内容变化
        self.body = ctk.CTkFrame(self._canvas, fg_color="transparent")
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self.body, anchor="nw"
        )

        # Canvas 滚动区域随内容更新
        def _on_frame_configure(_):
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))

        def _on_canvas_configure(e):
            # Canvas 宽度固定为容器宽度，内容永远不换行
            self._canvas.itemconfig(self._canvas_window, width=e.width)

        self.body.bind("<<WidgetChanged>>", _on_frame_configure)
        self._canvas.bind("<Configure>", _on_canvas_configure)

        # 鼠标滚轮支持
        def _on_mousewheel(event):
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self._canvas.bind_all("<MouseWheel>", _on_mousewheel)

        ctk.CTkLabel(self.body, text="设置",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(16, 10))

        self._build_cooldown()
        self._divider()
        self._build_tg_search_calib()
        self._divider()
        self._build_ocr_region()
        self._divider()
        self._build_send_check_region()
        self._divider()
        self._build_x_calib()
        self._divider()
        self._build_tg_creds(
            purpose="parser",
            title="TG 账号 A — 群管理员解析",
            desc=("用于进入 TG 群、提取 Owner / Admin，然后退群。\n"
                  "对应「🔬 解析」页左侧的「TG 管理员解析」功能。\n"
                  f"Session 文件：{os.path.join(config.DATA_DIR, 'tg_session_parser.session')}"),
        )
        self._divider()
        self._build_tg_creds(
            purpose="left",
            title="TG 账号 B — 离群用户扫描",
            desc=("用于扫描账号所在的小群历史消息，找出已离群的用户。\n"
                  "对应「🔬 解析」页右侧的「离群用户扫描」功能。\n"
                  f"Session 文件：{os.path.join(config.DATA_DIR, 'tg_session_left.session')}"),
        )
        self._divider()
        self._build_tg_creds(
            purpose="sender",
            title="TG 账号 C — DM 发送",
            desc=("发送 DM 时需在桌面登录此账号。\n"
                  "当前发送方式为 OCR + PyAutoGUI 操作桌面 Telegram，\n"
                  "API 信息在此处存档，发送时程序不直接调用 Telethon。\n"
                  f"Session 文件（备用）：{os.path.join(config.DATA_DIR, 'tg_session_sender.session')}"),
            note="发送账号使用桌面 Telegram 操作，此处 API 仅作记录",
        )
        self._divider()
        self._build_deepseek()
        self._divider()
        self._build_preview()

    # ════════════════ DM 冷却 ═════════════════════════════════
    def _build_cooldown(self):
        sec = self._section("DM 冷却时间")

        ctk.CTkLabel(
            sec,
            text="发送 DM 后，在冷却期内不再向同一联系人重复发送。\n"
                 "冷却期结束后该联系人重新进入待发队列，可进行第二轮触达。\n"
                 "设为 0 天 0 小时 = 关闭冷却（发过的联系人永远不再发）。",
            text_color="gray", justify="left", wraplength=720,
        ).pack(anchor="w", padx=16, pady=(0, 8))

        row = ctk.CTkFrame(sec, fg_color="transparent")
        row.pack(anchor="w", padx=16, pady=(0, 6))
        ctk.CTkLabel(row, text="冷却时长：").pack(side="left")
        self.e_days = ctk.CTkEntry(row, width=64, justify="center")
        self.e_days.pack(side="left", padx=(6, 2))
        ctk.CTkLabel(row, text="天").pack(side="left")
        self.e_hours = ctk.CTkEntry(row, width=64, justify="center")
        self.e_hours.pack(side="left", padx=(10, 2))
        ctk.CTkLabel(row, text="小时").pack(side="left")

        self.lbl_cooldown_status = ctk.CTkLabel(
            sec, text="", text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_cooldown_status.pack(anchor="w", padx=16, pady=(2, 2))

        self.lbl_cooldown_effect = ctk.CTkLabel(
            sec, text="", text_color="gray", font=ctk.CTkFont(size=11), justify="left")
        self.lbl_cooldown_effect.pack(anchor="w", padx=16, pady=(0, 8))

        btn_row = ctk.CTkFrame(sec, fg_color="transparent")
        btn_row.pack(anchor="w", padx=16, pady=(0, 14))
        ctk.CTkButton(btn_row, text="💾 保存冷却设置", width=130,
                      command=self._save_cooldown).pack(side="left", padx=(0, 10))
        ctk.CTkButton(btn_row, text="预览待发数量", width=120,
                      fg_color="gray40", command=self._preview).pack(side="left")

    # ════════════════ TG 搜索栏坐标校准 ══════════════════════
    def _build_tg_search_calib(self):
        sec = self._section("TG 搜索栏位置校准")

        ctk.CTkLabel(
            sec,
            text="TG DM 发送时，程序需要点击桌面 Telegram 的搜索栏输入用户名。\n"
                 "如果搜索栏位置不准确（如屏幕分辨率不同），请重新校准。\n"
                 f"默认位置：{config.TG_SEARCH_BAR_POS}",
            text_color="gray", justify="left", wraplength=720,
        ).pack(anchor="w", padx=16, pady=(0, 8))

        # 当前坐标显示
        self.lbl_tg_search_pos = ctk.CTkLabel(
            sec, text="", text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_tg_search_pos.pack(anchor="w", padx=16, pady=(0, 4))

        # 校准提示 + 倒计时
        self.lbl_tg_calib_hint = ctk.CTkLabel(
            sec, text="点击「校准搜索栏」后将鼠标移到 Telegram 搜索栏上等待倒计时",
            text_color="gray", justify="left", wraplength=720)
        self.lbl_tg_calib_hint.pack(anchor="w", padx=16, pady=(0, 2))

        self.lbl_tg_countdown = ctk.CTkLabel(
            sec, text="", font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#2196F3")
        self.lbl_tg_countdown.pack(anchor="w", padx=16, pady=(0, 4))

        btn_row = ctk.CTkFrame(sec, fg_color="transparent")
        btn_row.pack(anchor="w", padx=16, pady=(0, 14))

        self.btn_tg_calib = ctk.CTkButton(
            btn_row, text="🎯 校准搜索栏", width=130,
            command=self._start_tg_calib)
        self.btn_tg_calib.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="移到搜索栏", width=110, fg_color="gray40",
            command=self._move_to_tg_search).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="重置默认", width=90, fg_color="gray40",
            command=self._reset_tg_search).pack(side="left")

    def _start_tg_calib(self):
        self.btn_tg_calib.configure(state="disabled")
        threading.Thread(target=self._tg_calib_flow, daemon=True).start()

    def _tg_calib_flow(self):
        try:
            import pyautogui
        except ImportError:
            self.lbl_tg_calib_hint.configure(
                text="缺少 pyautogui，请运行 pip install pyautogui", text_color="#F44336")
            self.btn_tg_calib.configure(state="normal")
            return

        try:
            self.lbl_tg_calib_hint.configure(
                text="请将鼠标移到桌面 Telegram 的搜索栏上，不要点击，倒计时结束时自动记录位置。",
                text_color="white")
            for i in range(5, 0, -1):
                self.lbl_tg_countdown.configure(text=f"记录搜索栏：{i} 秒")
                time.sleep(1)
            self.lbl_tg_countdown.configure(text="📍 已记录！")

            x, y = pyautogui.position()
            db.save_tg_search_pos(x, y)
            time.sleep(0.5)
            self.lbl_tg_countdown.configure(text="")
            self.lbl_tg_calib_hint.configure(
                text=f"校准完成！搜索栏位置已保存为 ({x}, {y})",
                text_color="#4CAF50")
            self._refresh_tg_search_label()
        except Exception as e:
            self.lbl_tg_calib_hint.configure(
                text=f"校准出错：{e}", text_color="#F44336")
        finally:
            self.btn_tg_calib.configure(state="normal")

    def _move_to_tg_search(self):
        try:
            import pyautogui
            x, y = db.get_tg_search_pos()
            pyautogui.moveTo(x, y, duration=0.3)
        except ImportError:
            messagebox.showwarning("缺少依赖", "请运行 pip install pyautogui")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _reset_tg_search(self):
        db.save_tg_search_pos(*config.TG_SEARCH_BAR_POS)
        self._refresh_tg_search_label()
        self.lbl_tg_calib_hint.configure(
            text=f"已重置为默认位置 {config.TG_SEARCH_BAR_POS}", text_color="gray")

    def _refresh_tg_search_label(self):
        x, y = db.get_tg_search_pos()
        self.lbl_tg_search_pos.configure(
            text=f"当前搜索栏位置：({x}, {y})", text_color="#4CAF50")

    # ════════════════ OCR 截图区域 ═══════════════════════════
    def _build_ocr_region(self):
        sec = self._section("TG OCR 截图区域")
        self._ocr_sec = sec

        ctk.CTkLabel(
            sec,
            text="发送 TG DM 时，OCR 会截取屏幕上这个区域来识别搜索结果。\n"
                 "可手动填写数值，也可点「校准」用鼠标定位各边界。\n"
                 "默认值：top=80  left=0  width=400  height=800",
            text_color="gray", justify="left", wraplength=720,
        ).pack(anchor="w", padx=16, pady=(0, 8))

        # 每个字段一行：标签 | 输入框 | 校准按钮 | 说明
        form = ctk.CTkFrame(sec, fg_color="transparent")
        form.pack(anchor="w", padx=16, pady=(0, 4))

        fields = [
            ("top",    "_ocr_top",    "80",  "移鼠标到截图区域顶边  →  记录 Y 坐标"),
            ("left",   "_ocr_left",   "0",   "移鼠标到截图区域左边  →  记录 X 坐标"),
            ("width",  "_ocr_width",  "400", "移鼠标到截图区域右边  →  计算 X − left"),
            ("height", "_ocr_height", "800", "移鼠标到截图区域底边  →  计算 Y − top"),
        ]
        self._ocr_calib_btns = {}
        for row, (field, attr, default, hint) in enumerate(fields):
            ctk.CTkLabel(form, text=f"{field}：", width=55, anchor="e").grid(
                row=row, column=0, padx=(0, 4), pady=4, sticky="e")
            entry = ctk.CTkEntry(form, width=72, justify="center",
                                 placeholder_text=default)
            entry.grid(row=row, column=1, padx=(0, 6), pady=4)
            setattr(self, attr, entry)

            btn = ctk.CTkButton(form, text="校准", width=56,
                                fg_color="gray40",
                                command=lambda f=field: self._start_ocr_calib(f))
            btn.grid(row=row, column=2, padx=(0, 10), pady=4)
            self._ocr_calib_btns[field] = btn

            ctk.CTkLabel(form, text=hint, text_color="gray",
                         font=ctk.CTkFont(size=11)).grid(
                row=row, column=3, padx=(0, 8), pady=4, sticky="w")

        # 倒计时标签
        self.lbl_ocr_countdown = ctk.CTkLabel(
            sec, text="", font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#2196F3")
        self.lbl_ocr_countdown.pack(anchor="w", padx=16, pady=(0, 4))

        # 操作按钮行
        btn_row = ctk.CTkFrame(sec, fg_color="transparent")
        btn_row.pack(anchor="w", padx=16, pady=(0, 8))

        ctk.CTkButton(btn_row, text="💾 保存", width=90,
                      command=self._save_ocr_region).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="🔍 预览截图", width=110,
                      command=self._preview_ocr_region).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="重置默认", width=90, fg_color="gray40",
                      command=self._reset_ocr_region).pack(side="left")

        self.lbl_ocr_status = ctk.CTkLabel(
            sec, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self.lbl_ocr_status.pack(anchor="w", padx=16, pady=(0, 4))

        # 预览图容器（初始隐藏）
        self._ocr_preview_frame = ctk.CTkFrame(sec, fg_color=("gray80", "gray25"))
        self._ocr_preview_label = ctk.CTkLabel(self._ocr_preview_frame, text="")
        self._ocr_preview_label.pack(padx=8, pady=8)

    def _start_ocr_calib(self, field):
        for btn in self._ocr_calib_btns.values():
            btn.configure(state="disabled")
        threading.Thread(target=self._ocr_calib_flow, args=(field,), daemon=True).start()

    def _ocr_calib_flow(self, field):
        try:
            import pyautogui
        except ImportError:
            self.lbl_ocr_status.configure(
                text="缺少 pyautogui，请运行 pip install pyautogui", text_color="#F44336")
            for btn in self._ocr_calib_btns.values():
                btn.configure(state="normal")
            return

        hints = {
            "top":    "将鼠标移到截图区域顶边",
            "left":   "将鼠标移到截图区域左边",
            "width":  "将鼠标移到截图区域右边",
            "height": "将鼠标移到截图区域底边",
        }
        self.lbl_ocr_status.configure(
            text=f"校准 {field}：{hints[field]}，倒计时结束自动记录", text_color="white")

        for i in range(3, 0, -1):
            self.lbl_ocr_countdown.configure(text=f"记录 {field}：{i} 秒")
            time.sleep(1)
        self.lbl_ocr_countdown.configure(text="📍 已记录！")

        mx, my = pyautogui.position()

        try:
            if field == "top":
                value = my
            elif field == "left":
                value = mx
            elif field == "width":
                left = int(self._ocr_left.get() or 0)
                value = max(1, mx - left)
            else:  # height
                top = int(self._ocr_top.get() or 0)
                value = max(1, my - top)
        except ValueError:
            self.lbl_ocr_status.configure(
                text="计算失败：请先填写 left/top 的值再校准 width/height", text_color="#F44336")
            self.lbl_ocr_countdown.configure(text="")
            for btn in self._ocr_calib_btns.values():
                btn.configure(state="normal")
            return

        entry = getattr(self, f"_ocr_{field}")
        entry.delete(0, "end")
        entry.insert(0, str(value))

        time.sleep(0.4)
        self.lbl_ocr_countdown.configure(text="")
        self.lbl_ocr_status.configure(
            text=f"校准完成：{field} = {value}（鼠标位置 x={mx}, y={my}）",
            text_color="#4CAF50")

        for btn in self._ocr_calib_btns.values():
            btn.configure(state="normal")

    def _save_ocr_region(self):
        try:
            top    = int(self._ocr_top.get()    or 80)
            left   = int(self._ocr_left.get()   or 0)
            width  = int(self._ocr_width.get()  or 400)
            height = int(self._ocr_height.get() or 800)
        except ValueError:
            messagebox.showwarning("格式错误", "请填写整数"); return
        if width <= 0 or height <= 0:
            messagebox.showwarning("格式错误", "width/height 必须大于 0"); return
        db.save_ocr_region(top, left, width, height)
        self.lbl_ocr_status.configure(
            text=f"已保存：top={top}  left={left}  width={width}  height={height}",
            text_color="#4CAF50")

    def _preview_ocr_region(self):
        try:
            top    = int(self._ocr_top.get()    or 80)
            left   = int(self._ocr_left.get()   or 0)
            width  = int(self._ocr_width.get()  or 400)
            height = int(self._ocr_height.get() or 800)
        except ValueError:
            messagebox.showwarning("格式错误", "请填写整数"); return

        try:
            import mss
            from PIL import Image
            import customtkinter as ctk_inner
        except ImportError as e:
            messagebox.showwarning("缺少依赖", str(e)); return

        try:
            with mss.mss() as sct:
                region  = {"top": top, "left": left, "width": width, "height": height}
                sct_img = sct.grab(region)
                img = Image.frombytes("RGB", (sct_img.width, sct_img.height),
                                      sct_img.bgra, "raw", "BGRX")

            # 缩放到最大 380×600 以适配面板
            img.thumbnail((380, 600), Image.LANCZOS)

            ctk_img = ctk_inner.CTkImage(light_image=img, dark_image=img,
                                         size=(img.width, img.height))
            # 先销毁旧图，再设置新图，防止图片资源累积
            old = getattr(self._ocr_preview_label, "image", None)
            if old is not None:
                self._ocr_preview_label.configure(image="")
                try:
                    old.cget("light_image").close()
                except Exception:
                    pass
            self._ocr_preview_label.configure(image=ctk_img, text="")
            self._ocr_preview_label.image = ctk_img  # 防 GC
            self._ocr_preview_frame.pack(fill="x", padx=16, pady=(0, 12))

            self.lbl_ocr_status.configure(
                text=f"预览：top={top}  left={left}  width={width}  height={height}"
                     f"  →  实际截图 {sct_img.width}×{sct_img.height}",
                text_color="#2196F3")
        except Exception as e:
            messagebox.showerror("截图失败", str(e))

    def _reset_ocr_region(self):
        db.save_ocr_region(80, 0, 400, 800)
        for attr, val in [("_ocr_top", "80"), ("_ocr_left", "0"),
                          ("_ocr_width", "400"), ("_ocr_height", "800")]:
            e = getattr(self, attr)
            e.delete(0, "end")
            e.insert(0, val)
        self.lbl_ocr_status.configure(text="已重置为默认值", text_color="gray")

    # ════════════════ 发送检测截图区域 ═══════════════════════
    def _build_send_check_region(self):
        sec = self._section("TG 发送检测截图区域")

        ctk.CTkLabel(
            sec,
            text="发送 DM 后，OCR 会截取此区域检测是否出现「账号受限」对话框。\n"
                 "未配置时自动使用屏幕中间 1/2 区域。\n"
                 "建议：将 Telegram 摆好位置后，框选对话框可能出现的范围。",
            text_color="gray", justify="left", wraplength=720,
        ).pack(anchor="w", padx=16, pady=(0, 8))

        form = ctk.CTkFrame(sec, fg_color="transparent")
        form.pack(anchor="w", padx=16, pady=(0, 4))

        fields = [
            ("top",    "_sc_top",    "", "移鼠标到检测区域顶边  →  记录 Y 坐标"),
            ("left",   "_sc_left",   "", "移鼠标到检测区域左边  →  记录 X 坐标"),
            ("width",  "_sc_width",  "", "移鼠标到检测区域右边  →  计算 X − left"),
            ("height", "_sc_height", "", "移鼠标到检测区域底边  →  计算 Y − top"),
        ]
        self._sc_calib_btns = {}
        for row, (field, attr, default, hint) in enumerate(fields):
            ctk.CTkLabel(form, text=f"{field}：", width=55, anchor="e").grid(
                row=row, column=0, padx=(0, 4), pady=4, sticky="e")
            entry = ctk.CTkEntry(form, width=72, justify="center",
                                 placeholder_text="自动")
            entry.grid(row=row, column=1, padx=(0, 6), pady=4)
            setattr(self, attr, entry)

            btn = ctk.CTkButton(form, text="校准", width=56,
                                fg_color="gray40",
                                command=lambda f=field: self._start_sc_calib(f))
            btn.grid(row=row, column=2, padx=(0, 10), pady=4)
            self._sc_calib_btns[field] = btn

            ctk.CTkLabel(form, text=hint, text_color="gray",
                         font=ctk.CTkFont(size=11)).grid(
                row=row, column=3, padx=(0, 8), pady=4, sticky="w")

        self.lbl_sc_countdown = ctk.CTkLabel(
            sec, text="", font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#2196F3")
        self.lbl_sc_countdown.pack(anchor="w", padx=16, pady=(0, 4))

        btn_row = ctk.CTkFrame(sec, fg_color="transparent")
        btn_row.pack(anchor="w", padx=16, pady=(0, 8))

        ctk.CTkButton(btn_row, text="💾 保存", width=90,
                      command=self._save_sc_region).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="🔍 预览截图", width=110,
                      command=self._preview_sc_region).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="重置自动", width=90, fg_color="gray40",
                      command=self._reset_sc_region).pack(side="left")

        self.lbl_sc_status = ctk.CTkLabel(
            sec, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self.lbl_sc_status.pack(anchor="w", padx=16, pady=(0, 4))

        self._sc_preview_frame = ctk.CTkFrame(sec, fg_color=("gray80", "gray25"))
        self._sc_preview_label = ctk.CTkLabel(self._sc_preview_frame, text="")
        self._sc_preview_label.pack(padx=8, pady=8)

    def _start_sc_calib(self, field):
        for btn in self._sc_calib_btns.values():
            btn.configure(state="disabled")
        threading.Thread(target=self._sc_calib_flow, args=(field,), daemon=True).start()

    def _sc_calib_flow(self, field):
        try:
            import pyautogui
        except ImportError:
            self.lbl_sc_status.configure(
                text="缺少 pyautogui", text_color="#F44336")
            for btn in self._sc_calib_btns.values():
                btn.configure(state="normal")
            return

        hints = {
            "top":    "将鼠标移到检测区域顶边",
            "left":   "将鼠标移到检测区域左边",
            "width":  "将鼠标移到检测区域右边",
            "height": "将鼠标移到检测区域底边",
        }
        self.lbl_sc_status.configure(
            text=f"校准 {field}：{hints[field]}，倒计时结束自动记录",
            text_color="white")

        for i in range(3, 0, -1):
            self.lbl_sc_countdown.configure(text=f"记录 {field}：{i} 秒")
            time.sleep(1)
        self.lbl_sc_countdown.configure(text="📍 已记录！")

        mx, my = pyautogui.position()

        try:
            if field == "top":
                value = my
            elif field == "left":
                value = mx
            elif field == "width":
                left = int(self._sc_left.get() or 0)
                value = max(1, mx - left)
            else:
                top = int(self._sc_top.get() or 0)
                value = max(1, my - top)
        except ValueError:
            self.lbl_sc_status.configure(
                text="计算失败：请先填写 left/top 再校准 width/height",
                text_color="#F44336")
            self.lbl_sc_countdown.configure(text="")
            for btn in self._sc_calib_btns.values():
                btn.configure(state="normal")
            return

        entry = getattr(self, f"_sc_{field}")
        entry.delete(0, "end")
        entry.insert(0, str(value))

        time.sleep(0.4)
        self.lbl_sc_countdown.configure(text="")
        self.lbl_sc_status.configure(
            text=f"校准完成：{field} = {value}（鼠标位置 x={mx}, y={my}）",
            text_color="#4CAF50")
        for btn in self._sc_calib_btns.values():
            btn.configure(state="normal")

    def _save_sc_region(self):
        try:
            top    = int(self._sc_top.get())
            left   = int(self._sc_left.get())
            width  = int(self._sc_width.get())
            height = int(self._sc_height.get())
        except ValueError:
            messagebox.showwarning("格式错误", "请填写完整的整数，或点「重置自动」使用自动模式")
            return
        if width <= 0 or height <= 0:
            messagebox.showwarning("格式错误", "width/height 必须大于 0")
            return
        db.save_send_check_region(top, left, width, height)
        self.lbl_sc_status.configure(
            text=f"已保存：top={top}  left={left}  width={width}  height={height}",
            text_color="#4CAF50")

    def _preview_sc_region(self):
        try:
            top    = int(self._sc_top.get())
            left   = int(self._sc_left.get())
            width  = int(self._sc_width.get())
            height = int(self._sc_height.get())
        except ValueError:
            messagebox.showwarning("格式错误", "请先填写完整数值再预览")
            return
        try:
            import mss
            from PIL import Image
            import customtkinter as ctk_inner
        except ImportError as e:
            messagebox.showwarning("缺少依赖", str(e))
            return
        try:
            with mss.mss() as sct:
                sct_img = sct.grab({"top": top, "left": left,
                                    "width": width, "height": height})
                img = Image.frombytes("RGB", (sct_img.width, sct_img.height),
                                      sct_img.bgra, "raw", "BGRX")
            img.thumbnail((380, 600), Image.LANCZOS)
            ctk_img = ctk_inner.CTkImage(light_image=img, dark_image=img,
                                         size=(img.width, img.height))
            # 先销毁旧图，再设置新图
            old = getattr(self._sc_preview_label, "image", None)
            if old is not None:
                self._sc_preview_label.configure(image="")
                try:
                    old.cget("light_image").close()
                except Exception:
                    pass
            self._sc_preview_label.configure(image=ctk_img, text="")
            self._sc_preview_label.image = ctk_img
            self._sc_preview_frame.pack(fill="x", padx=16, pady=(0, 12))
            self.lbl_sc_status.configure(
                text=f"预览：top={top}  left={left}  width={width}  height={height}"
                     f"  →  实际截图 {sct_img.width}×{sct_img.height}",
                text_color="#2196F3")
        except Exception as e:
            messagebox.showerror("截图失败", str(e))

    def _reset_sc_region(self):
        for key in ["send_check_top", "send_check_left",
                    "send_check_width", "send_check_height"]:
            db.save_setting(key, None)
        for attr in ["_sc_top", "_sc_left", "_sc_width", "_sc_height"]:
            e = getattr(self, attr)
            e.delete(0, "end")
        self.lbl_sc_status.configure(text="已重置为自动模式（屏幕中间 1/2）", text_color="gray")

    # ════════════════ X DM 坐标校准 ══════════════════════════
    def _build_x_calib(self):
        sec = self._section("X (Twitter) DM 坐标校准")

        ctk.CTkLabel(
            sec,
            text="X DM 发送时，程序需要点击「Message」按钮和消息输入框。\n"
                 "首次使用或更换显示器时，请重新完成两步校准。",
            text_color="gray", justify="left", wraplength=720,
        ).pack(anchor="w", padx=16, pady=(0, 8))

        # 当前坐标显示
        coord_card = ctk.CTkFrame(sec, fg_color=("gray80", "gray30"))
        coord_card.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(coord_card, text="已保存坐标",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=12, pady=(8, 2))
        self.lbl_x_dm_pos   = ctk.CTkLabel(coord_card, text="DM 按钮：未校准", text_color="gray")
        self.lbl_x_dm_pos.pack(anchor="w", padx=12)
        self.lbl_x_chat_pos = ctk.CTkLabel(coord_card, text="消息输入框：未校准", text_color="gray")
        self.lbl_x_chat_pos.pack(anchor="w", padx=12, pady=(0, 8))
        self._refresh_x_pos_labels()

        # 校准提示 + 倒计时
        self.lbl_x_calib_hint = ctk.CTkLabel(
            sec, text="点击「开始校准」按照步骤引导记录两个坐标",
            text_color="gray", justify="left", wraplength=720)
        self.lbl_x_calib_hint.pack(anchor="w", padx=16, pady=(0, 2))

        self.lbl_x_countdown = ctk.CTkLabel(
            sec, text="", font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#2196F3")
        self.lbl_x_countdown.pack(anchor="w", padx=16, pady=(0, 4))

        # 校准按钮行
        calib_row = ctk.CTkFrame(sec, fg_color="transparent")
        calib_row.pack(anchor="w", padx=16, pady=(0, 8))

        self.btn_x_calib = ctk.CTkButton(
            calib_row, text="🎯 开始校准", width=110,
            command=self._start_x_calib)
        self.btn_x_calib.pack(side="left", padx=(0, 8))

        ctk.CTkButton(calib_row, text="重置坐标", width=90, fg_color="gray40",
                      command=self._reset_x_calib).pack(side="left")

        # 移动光标测试按钮行
        move_row = ctk.CTkFrame(sec, fg_color="transparent")
        move_row.pack(anchor="w", padx=16, pady=(0, 14))

        ctk.CTkButton(
            move_row, text="移到 DM 按钮", width=120, fg_color="gray40",
            command=self._move_to_x_dm).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            move_row, text="移到消息输入框", width=130, fg_color="gray40",
            command=self._move_to_x_chat).pack(side="left")

    def _start_x_calib(self):
        self.btn_x_calib.configure(state="disabled")
        threading.Thread(target=self._x_calib_flow, daemon=True).start()

    def _x_calib_flow(self):
        try:
            import pyautogui
        except ImportError:
            self.lbl_x_calib_hint.configure(
                text="缺少 pyautogui，请运行 pip install pyautogui", text_color="#F44336")
            self.btn_x_calib.configure(state="normal")
            return

        try:
            # 步骤 1：DM 按钮
            self.lbl_x_calib_hint.configure(
                text="步骤 1/2 — DM 按钮\n"
                     "在 Chrome 中打开任意 Twitter 用户主页（已登录），\n"
                     "将鼠标悬停在「Message」按钮上，不要点击。\n"
                     "倒计时结束时自动记录鼠标位置。",
                text_color="white")
            for i in range(5, 0, -1):
                self.lbl_x_countdown.configure(text=f"记录 DM 按钮：{i} 秒")
                time.sleep(1)
            self.lbl_x_countdown.configure(text="📍 已记录！")
            dm_x, dm_y = pyautogui.position()
            os.makedirs(config.DATA_DIR, exist_ok=True)
            with open(config.DM_POS_FILE, 'w') as f:
                f.write(f"{dm_x},{dm_y}")
            time.sleep(0.5)

            # 步骤 2：消息输入框
            self.lbl_x_calib_hint.configure(
                text=f"✓ DM 按钮：({dm_x}, {dm_y})\n\n"
                     "步骤 2/2 — 消息输入框\n"
                     "手动点击「Message」按钮，等待 DM 对话框打开，\n"
                     "将鼠标悬停在消息输入框上。倒计时结束时自动记录。",
                text_color="white")
            for i in range(8, 0, -1):
                self.lbl_x_countdown.configure(text=f"记录输入框：{i} 秒")
                time.sleep(1)
            self.lbl_x_countdown.configure(text="📍 已记录！")
            chat_x, chat_y = pyautogui.position()
            with open(config.CHAT_POS_FILE, 'w') as f:
                f.write(f"{chat_x},{chat_y}")
            time.sleep(0.5)

            self.lbl_x_countdown.configure(text="")
            self.lbl_x_calib_hint.configure(
                text=f"校准完成！  DM 按钮:({dm_x},{dm_y})  输入框:({chat_x},{chat_y})",
                text_color="#4CAF50")
            self._refresh_x_pos_labels()
        except Exception as e:
            self.lbl_x_calib_hint.configure(text=f"校准出错：{e}", text_color="#F44336")
        finally:
            self.btn_x_calib.configure(state="normal")

    def _move_to_x_dm(self):
        try:
            import pyautogui
            x, y = open(config.DM_POS_FILE).read().strip().split(',')
            pyautogui.moveTo(int(x), int(y), duration=0.3)
        except FileNotFoundError:
            messagebox.showwarning("未校准", "请先完成 DM 按钮校准")
        except ImportError:
            messagebox.showwarning("缺少依赖", "请运行 pip install pyautogui")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _move_to_x_chat(self):
        try:
            import pyautogui
            x, y = open(config.CHAT_POS_FILE).read().strip().split(',')
            pyautogui.moveTo(int(x), int(y), duration=0.3)
        except FileNotFoundError:
            messagebox.showwarning("未校准", "请先完成消息输入框校准")
        except ImportError:
            messagebox.showwarning("缺少依赖", "请运行 pip install pyautogui")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _reset_x_calib(self):
        for f in [config.DM_POS_FILE, config.CHAT_POS_FILE]:
            if os.path.exists(f):
                os.remove(f)
        self._refresh_x_pos_labels()
        self.lbl_x_calib_hint.configure(text="坐标已重置，请重新校准", text_color="gray")

    def _refresh_x_pos_labels(self):
        try:
            x, y = open(config.DM_POS_FILE).read().strip().split(',')
            self.lbl_x_dm_pos.configure(text=f"DM 按钮：({x}, {y})", text_color="#4CAF50")
        except Exception:
            self.lbl_x_dm_pos.configure(text="DM 按钮：未校准", text_color="gray")
        try:
            x, y = open(config.CHAT_POS_FILE).read().strip().split(',')
            self.lbl_x_chat_pos.configure(text=f"消息输入框：({x}, {y})", text_color="#4CAF50")
        except Exception:
            self.lbl_x_chat_pos.configure(text="消息输入框：未校准", text_color="gray")

    # ════════════════ TG 账号凭证区（通用） ══════════════════
    def _build_tg_creds(self, purpose, title, desc, note=None):
        sec = self._section(title)

        ctk.CTkLabel(sec, text=desc, text_color="gray",
                     justify="left", wraplength=720).pack(
                         anchor="w", padx=16, pady=(0, 8))

        if note:
            ctk.CTkLabel(sec, text=f"  ⚠ {note}",
                         text_color="#FF9800", font=ctk.CTkFont(size=11),
                         justify="left").pack(anchor="w", padx=16, pady=(0, 6))

        form = ctk.CTkFrame(sec, fg_color="transparent")
        form.pack(anchor="w", padx=16, pady=(0, 4))

        # API ID
        ctk.CTkLabel(form, text="API ID：", width=80, anchor="w").grid(
            row=0, column=0, pady=4, sticky="w")
        e_id = ctk.CTkEntry(form, width=200, placeholder_text="数字，如 12345678")
        e_id.grid(row=0, column=1, padx=(4, 0), pady=4)

        # API Hash
        ctk.CTkLabel(form, text="API Hash：", width=80, anchor="w").grid(
            row=1, column=0, pady=4, sticky="w")
        e_hash = ctk.CTkEntry(form, width=340, placeholder_text="32位十六进制字符串")
        e_hash.grid(row=1, column=1, padx=(4, 0), pady=4)

        # 状态标签
        lbl_status = ctk.CTkLabel(sec, text="", text_color="gray",
                                   font=ctk.CTkFont(size=11))
        lbl_status.pack(anchor="w", padx=16, pady=(2, 2))

        # 保存按钮
        btn_row = ctk.CTkFrame(sec, fg_color="transparent")
        btn_row.pack(anchor="w", padx=16, pady=(4, 14))

        p = purpose  # closure

        def save_creds():
            api_id   = e_id.get().strip()
            api_hash = e_hash.get().strip()
            if not api_id or not api_hash:
                messagebox.showwarning("格式错误", "API ID 和 API Hash 不能为空")
                return
            if not api_id.isdigit():
                messagebox.showwarning("格式错误", "API ID 必须是纯数字")
                return
            if len(api_hash) != 32:
                messagebox.showwarning("格式错误", "API Hash 应为 32 位字符串")
                return
            db.save_tg_credentials(p, api_id, api_hash)
            lbl_status.configure(
                text=f"已保存  API_ID={api_id}  Hash={api_hash[:6]}…{api_hash[-4:]}",
                text_color="#4CAF50")

        def get_from_mytg():
            import webbrowser
            webbrowser.open("https://my.telegram.org/auth")

        ctk.CTkButton(btn_row, text="💾 保存", width=90,
                      command=save_creds).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="获取 API → my.telegram.org", width=200,
                      fg_color="gray40", command=get_from_mytg).pack(side="left")

        # 登录验证按钮（仅 parser / left 需要，sender 用桌面 TG 不需要）
        if purpose != "sender":
            def do_login():
                btn_login.configure(state="disabled")
                lbl_status.configure(text="正在登录...", text_color="#FF9800")
                def _login_thread():
                    from workers.telethon_auth import login_telethon
                    result = login_telethon(p, log_callback=lambda msg: lbl_status.configure(text=msg, text_color="#2196F3"))
                    if result:
                        lbl_status.configure(
                            text=f"登录成功：{result}", text_color="#4CAF50")
                    else:
                        lbl_status.configure(
                            text="登录失败或已取消", text_color="#F44336")
                    btn_login.configure(state="normal")
                threading.Thread(target=_login_thread, daemon=True).start()

            btn_login = ctk.CTkButton(btn_row, text="登录验证", width=90,
                                      fg_color="#2196F3", hover_color="#1976D2",
                                      command=do_login)
            btn_login.pack(side="left", padx=(10, 0))
            setattr(self, f"_btn_login_{purpose}", btn_login)

        # 挂到 self 方便 _load_all 读取
        setattr(self, f"_e_id_{purpose}",     e_id)
        setattr(self, f"_e_hash_{purpose}",   e_hash)
        setattr(self, f"_lbl_status_{purpose}", lbl_status)

    # ════════════════ DeepSeek API ═══════════════════════════
    def _build_deepseek(self):
        sec = self._section("DeepSeek API — 官方链接智能筛选")

        ctk.CTkLabel(
            sec,
            text="爬虫从官网发现多个 TG / X 链接时，自动调用 DeepSeek 判断哪个是项目官方账号。\n"
                 "API Key 留空则跳过筛选，直接保存所有候选链接。",
            text_color="gray", justify="left", wraplength=720,
        ).pack(anchor="w", padx=16, pady=(0, 8))

        form = ctk.CTkFrame(sec, fg_color="transparent")
        form.pack(anchor="w", padx=16, pady=(0, 4))

        ctk.CTkLabel(form, text="API Key：", width=80, anchor="w").grid(
            row=0, column=0, pady=4, sticky="w")
        self.e_deepseek_key = ctk.CTkEntry(
            form, width=420, placeholder_text="sk-…", show="*")
        self.e_deepseek_key.grid(row=0, column=1, padx=(4, 0), pady=4)

        self.lbl_deepseek_status = ctk.CTkLabel(
            sec, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self.lbl_deepseek_status.pack(anchor="w", padx=16, pady=(2, 2))

        btn_row = ctk.CTkFrame(sec, fg_color="transparent")
        btn_row.pack(anchor="w", padx=16, pady=(4, 14))

        def save_key():
            key = self.e_deepseek_key.get().strip()
            db.save_setting("deepseek_api_key", key)
            if key:
                self.lbl_deepseek_status.configure(
                    text=f"已保存：{key[:8]}…{key[-4:]}", text_color="#4CAF50")
            else:
                self.lbl_deepseek_status.configure(
                    text="已清空（筛选功能已禁用）", text_color="gray")

        ctk.CTkButton(btn_row, text="💾 保存", width=90,
                      command=save_key).pack(side="left")

    # ════════════════ 待发预览 ════════════════════════════════
    def _build_preview(self):
        self.preview_frame = ctk.CTkFrame(self.body, fg_color=("gray85", "gray20"))
        self.preview_frame.pack(fill="x", padx=20, pady=(4, 16))
        ctk.CTkLabel(self.preview_frame, text="待发数量预览",
                     font=ctk.CTkFont(weight="bold")).pack(
                         anchor="w", padx=16, pady=(10, 4))
        self.lbl_preview = ctk.CTkLabel(
            self.preview_frame,
            text="点击「预览待发数量」查看当前冷却设置下各队列的待发数",
            text_color="gray", justify="left")
        self.lbl_preview.pack(anchor="w", padx=16, pady=(0, 12))

    # ════════════════ 加载已保存值 ════════════════════════════
    def _load_all(self):
        # 冷却
        days  = db.get_setting("cooldown_days",  "0")
        hours = db.get_setting("cooldown_hours", "0")
        self.e_days.delete(0, "end");  self.e_days.insert(0, days)
        self.e_hours.delete(0, "end"); self.e_hours.insert(0, hours)
        self._refresh_cooldown_labels(int(days), int(hours))

        # TG 搜索栏位置
        self._refresh_tg_search_label()

        # OCR 截图区域
        r = db.get_ocr_region()
        for attr, key in [("_ocr_top", "top"), ("_ocr_left", "left"),
                          ("_ocr_width", "width"), ("_ocr_height", "height")]:
            e = getattr(self, attr)
            e.delete(0, "end")
            e.insert(0, str(r[key]))

        # 发送检测截图区域（仅在 DB 有值时填入，否则留空显示 placeholder）
        for attr, key in [("_sc_top",    "send_check_top"),
                          ("_sc_left",   "send_check_left"),
                          ("_sc_width",  "send_check_width"),
                          ("_sc_height", "send_check_height")]:
            val = db.get_setting(key, "")
            if val:
                e = getattr(self, attr)
                e.delete(0, "end")
                e.insert(0, val)

        # DeepSeek API Key
        ds_key = db.get_setting("deepseek_api_key", "")
        self.e_deepseek_key.delete(0, "end")
        self.e_deepseek_key.insert(0, ds_key)
        if ds_key:
            self.lbl_deepseek_status.configure(
                text=f"当前：{ds_key[:8]}…{ds_key[-4:]}", text_color="gray")

        # 三组 TG 凭证
        for purpose in ("parser", "left", "sender"):
            api_id, api_hash, _ = db.get_tg_credentials(purpose)
            e_id   = getattr(self, f"_e_id_{purpose}")
            e_hash = getattr(self, f"_e_hash_{purpose}")
            lbl    = getattr(self, f"_lbl_status_{purpose}")

            e_id.delete(0, "end");   e_id.insert(0, str(api_id))
            e_hash.delete(0, "end"); e_hash.insert(0, api_hash)
            lbl.configure(
                text=f"当前：API_ID={api_id}  Hash={api_hash[:6]}…{api_hash[-4:]}",
                text_color="gray")

    # ════════════════ 冷却保存 / 刷新 ════════════════════════
    def _save_cooldown(self):
        try:
            days  = int(self.e_days.get()  or 0)
            hours = int(self.e_hours.get() or 0)
        except ValueError:
            messagebox.showwarning("格式错误", "天数和小时数请填整数"); return
        if days < 0 or hours < 0:
            messagebox.showwarning("格式错误", "不能为负数"); return
        if hours > 23:
            messagebox.showwarning("格式错误", "小时数范围 0–23"); return

        db.save_setting("cooldown_days",  str(days))
        db.save_setting("cooldown_hours", str(hours))
        self._refresh_cooldown_labels(days, hours)
        messagebox.showinfo("已保存", f"冷却时间已设为：{days} 天 {hours} 小时")

    def _refresh_cooldown_labels(self, days, hours):
        total_h = days * 24 + hours
        if total_h == 0:
            self.lbl_cooldown_status.configure(
                text="当前：关闭冷却（已发过的联系人不再发送）", text_color="gray")
            self.lbl_cooldown_effect.configure(
                text="效果：send_log 中有记录的联系人永远不会再出现在待发队列。")
        else:
            self.lbl_cooldown_status.configure(
                text=f"当前：冷却 {days} 天 {hours} 小时（共 {total_h} 小时）",
                text_color="#4CAF50")
            self.lbl_cooldown_effect.configure(
                text=f"效果：发送 DM 后 {total_h} 小时内同一联系人不再出现在待发队列；\n"
                     f"       {total_h} 小时后自动重新进入队列，可进行第二轮触达。")

    # ════════════════ 待发预览 ════════════════════════════════
    def _preview(self):
        try:
            days  = int(self.e_days.get()  or 0)
            hours = int(self.e_hours.get() or 0)
        except ValueError:
            messagebox.showwarning("格式错误", "请先填写正确的天数和小时数"); return

        db.save_setting("cooldown_days",  str(days))
        db.save_setting("cooldown_hours", str(hours))

        total_h  = days * 24 + hours
        imported = len(db.get_unsent_tg_imported_handles())
        parsed   = len(db.get_unsent_tg_parsed_handles())
        left     = len(db.get_unsent_tg_left_handles())
        x        = len(db.get_unsent_x_handles())

        cooldown_desc = (f"冷却 {days} 天 {hours} 小时（{total_h}h）"
                         if total_h > 0 else "关闭冷却")
        self.lbl_preview.configure(
            text=(f"冷却设置：{cooldown_desc}\n\n"
                  f"  TG 仓库导入   (imported) ：{imported} 条\n"
                  f"  TG 群解析管理员 (parsed)  ：{parsed} 条\n"
                  f"  TG 离群用户   (left)     ：{left} 条\n"
                  f"  X (Twitter)              ：{x} 条\n\n"
                  f"  TG 合计：{imported + parsed + left} 条"),
            text_color="white")
        self._refresh_cooldown_labels(days, hours)

    # ════════════════ 工具 ════════════════════════════════════
    def _section(self, title):
        """返回带标题的 section frame"""
        outer = ctk.CTkFrame(self.body, fg_color=("gray85", "gray20"))
        outer.pack(fill="x", padx=20, pady=6)
        ctk.CTkLabel(outer, text=title,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
                         anchor="w", padx=16, pady=(12, 6))
        return outer

    def _divider(self):
        ctk.CTkFrame(self.body, height=1,
                     fg_color=("gray70", "gray35")).pack(
                         fill="x", padx=20, pady=4)
