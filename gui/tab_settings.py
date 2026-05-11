"""
设置标签页 — DM 冷却 + TG 账号凭证（解析/离群扫描）+ DeepSeek API
"""
import threading
import tkinter.ttk as ttk
import customtkinter as ctk
from tkinter import messagebox

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
from gui.thread_bridge import enqueue


class SettingsTab:
    def __init__(self, parent):
        self.parent = parent
        self._build()
        self._load_all()

    # ════════════════ 整体布局 ════════════════════════════════
    def _build(self):
        container = ctk.CTkFrame(self.parent, fg_color="transparent")
        container.pack(fill="both", expand=True)

        v_scroll = ttk.Scrollbar(container, orient="vertical")
        v_scroll.pack(side="right", fill="y")

        fg = self.parent.cget("fg_color")
        if isinstance(fg, (list, tuple)):
            mode = ctk.get_appearance_mode()
            bg_color = fg[1] if mode == "Dark" else fg[0]
        else:
            bg_color = fg
        self._canvas = __import__('tkinter').Canvas(
            container, borderwidth=0, bg=bg_color,
            highlightthickness=0,
            yscrollcommand=v_scroll.set,
        )
        self._canvas.pack(side="left", fill="both", expand=True)
        v_scroll.configure(command=self._canvas.yview)

        self.body = ctk.CTkFrame(self._canvas, fg_color="transparent")
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self.body, anchor="nw"
        )

        def _on_frame_configure(_):
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))

        def _on_canvas_configure(e):
            self._canvas.itemconfig(self._canvas_window, width=e.width)

        self.body.bind("<Configure>", _on_frame_configure)
        self._canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            if event.delta:
                delta = event.delta
                if abs(delta) >= 120:
                    delta = delta // 120
                self._canvas.yview_scroll(-delta, "units")
            elif hasattr(event, 'num'):
                self._canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
        self._canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self._canvas.bind_all("<Button-4>", _on_mousewheel)
        self._canvas.bind_all("<Button-5>", _on_mousewheel)

        ctk.CTkLabel(self.body, text="设置",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(16, 10))

        self._build_cooldown()
        self._divider()
        self._build_tg_creds(
            purpose="parser",
            title="TG 账号 A — 群管理员解析",
            desc=("用于进入 TG 群、提取 Owner / Admin，然后退群。\n"
                  "对应「🔬 解析」页左侧的「TG 管理员解析」功能。\n"
                  f"Session 文件：{os.path.join('data', 'tg_session_parser.session')}"),
        )
        self._divider()
        self._build_tg_creds(
            purpose="left",
            title="TG 账号 B — 离群用户扫描",
            desc=("用于扫描账号所在的小群历史消息，找出已离群的用户。\n"
                  "对应「🔬 解析」页右侧的「离群用户扫描」功能。\n"
                  f"Session 文件：{os.path.join('data', 'tg_session_left.session')}"),
        )
        self._divider()
        self._build_gmail()
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

    # ════════════════ TG 账号凭证区（通用） ══════════════════
    def _build_tg_creds(self, purpose, title, desc):
        sec = self._section(title)

        ctk.CTkLabel(sec, text=desc, text_color="gray",
                     justify="left", wraplength=720).pack(
                         anchor="w", padx=16, pady=(0, 8))

        form = ctk.CTkFrame(sec, fg_color="transparent")
        form.pack(anchor="w", padx=16, pady=(0, 4))

        ctk.CTkLabel(form, text="API ID：", width=80, anchor="w").grid(
            row=0, column=0, pady=4, sticky="w")
        e_id = ctk.CTkEntry(form, width=200, placeholder_text="数字，如 12345678")
        e_id.grid(row=0, column=1, padx=(4, 0), pady=4)

        ctk.CTkLabel(form, text="API Hash：", width=80, anchor="w").grid(
            row=1, column=0, pady=4, sticky="w")
        e_hash = ctk.CTkEntry(form, width=340, placeholder_text="32位十六进制字符串")
        e_hash.grid(row=1, column=1, padx=(4, 0), pady=4)

        lbl_status = ctk.CTkLabel(sec, text="", text_color="gray",
                                   font=ctk.CTkFont(size=11))
        lbl_status.pack(anchor="w", padx=16, pady=(2, 2))

        btn_row = ctk.CTkFrame(sec, fg_color="transparent")
        btn_row.pack(anchor="w", padx=16, pady=(4, 14))

        p = purpose

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

        def do_login():
            btn_login.configure(state="disabled")
            lbl_status.configure(text="正在登录...", text_color="#FF9800")
            def _login_thread():
                from workers.telethon_auth import login_telethon
                def _log_cb(msg):
                    enqueue(lambda m=msg: lbl_status.configure(text=m, text_color="#2196F3"))
                result = login_telethon(p, log_callback=_log_cb)
                if result:
                    enqueue(lambda: lbl_status.configure(
                        text=f"登录成功：{result}", text_color="#4CAF50"))
                else:
                    enqueue(lambda: lbl_status.configure(
                        text="登录失败或已取消", text_color="#F44336"))
                enqueue(lambda: btn_login.configure(state="normal"))
            threading.Thread(target=_login_thread, daemon=True).start()

        btn_login = ctk.CTkButton(btn_row, text="登录验证", width=90,
                                  fg_color="#2196F3", hover_color="#1976D2",
                                  command=do_login)
        btn_login.pack(side="left", padx=(10, 0))
        setattr(self, f"_btn_login_{purpose}", btn_login)

        setattr(self, f"_e_id_{purpose}",       e_id)
        setattr(self, f"_e_hash_{purpose}",     e_hash)
        setattr(self, f"_lbl_status_{purpose}", lbl_status)

    # ════════════════ Gmail 账号 ═════════════════════════════
    def _build_gmail(self):
        sec = self._section("Gmail 账号 — 邮件发送")

        ctk.CTkLabel(
            sec,
            text="邮件发送使用 Gmail SMTP + App Password。\n"
                 "需在 Google 账号开启两步验证后生成「应用专用密码」。",
            text_color="gray", justify="left", wraplength=720,
        ).pack(anchor="w", padx=16, pady=(0, 8))

        form = ctk.CTkFrame(sec, fg_color="transparent")
        form.pack(anchor="w", padx=16, pady=(0, 4))

        ctk.CTkLabel(form, text="Gmail 地址：", width=100, anchor="w").grid(
            row=0, column=0, pady=4, sticky="w")
        self.e_gmail_addr = ctk.CTkEntry(form, width=280, placeholder_text="you@gmail.com")
        self.e_gmail_addr.grid(row=0, column=1, padx=(4, 0), pady=4)

        ctk.CTkLabel(form, text="App Password：", width=100, anchor="w").grid(
            row=1, column=0, pady=4, sticky="w")
        self.e_gmail_pw = ctk.CTkEntry(form, width=280, placeholder_text="16位应用密码", show="*")
        self.e_gmail_pw.grid(row=1, column=1, padx=(4, 0), pady=4)

        self.lbl_gmail_status = ctk.CTkLabel(
            sec, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self.lbl_gmail_status.pack(anchor="w", padx=16, pady=(2, 2))

        btn_row = ctk.CTkFrame(sec, fg_color="transparent")
        btn_row.pack(anchor="w", padx=16, pady=(4, 14))

        def save_gmail():
            addr = self.e_gmail_addr.get().strip()
            pw   = self.e_gmail_pw.get().strip()
            if not addr or not pw:
                messagebox.showwarning("格式错误", "地址和密码不能为空")
                return
            db.save_setting("gmail_address",      addr)
            db.save_setting("gmail_app_password", pw)
            self.lbl_gmail_status.configure(
                text=f"已保存：{addr}", text_color="#4CAF50")

        def open_apppassword():
            import webbrowser
            webbrowser.open("https://myaccount.google.com/apppasswords")

        ctk.CTkButton(btn_row, text="💾 保存", width=90,
                      command=save_gmail).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="生成 App Password →", width=180,
                      fg_color="gray40", command=open_apppassword).pack(side="left")

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
        days  = db.get_setting("cooldown_days",  "0")
        hours = db.get_setting("cooldown_hours", "0")
        self.e_days.delete(0, "end");  self.e_days.insert(0, days)
        self.e_hours.delete(0, "end"); self.e_hours.insert(0, hours)
        self._refresh_cooldown_labels(int(days), int(hours))

        gmail_addr = db.get_setting("gmail_address", "")
        gmail_pw   = db.get_setting("gmail_app_password", "")
        self.e_gmail_addr.delete(0, "end"); self.e_gmail_addr.insert(0, gmail_addr)
        self.e_gmail_pw.delete(0, "end");   self.e_gmail_pw.insert(0, gmail_pw)
        if gmail_addr:
            self.lbl_gmail_status.configure(
                text=f"当前：{gmail_addr}", text_color="gray")

        ds_key = db.get_setting("deepseek_api_key", "")
        self.e_deepseek_key.delete(0, "end")
        self.e_deepseek_key.insert(0, ds_key)
        if ds_key:
            self.lbl_deepseek_status.configure(
                text=f"当前：{ds_key[:8]}…{ds_key[-4:]}", text_color="gray")

        for purpose in ("parser", "left"):
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
