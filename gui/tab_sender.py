"""
发送标签页 — TG 发送控制 + X 发送控制
坐标校准已移至「⚙️ 设置」页
"""
import threading
import customtkinter as ctk
from tkinter import messagebox

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# TG / X 发送两平台统一走 Playwright（浏览器自动化，无需桌面 OCR/坐标）
from workers.tg_sender_web_worker import TGSenderWebWorker as TGSenderWorker
from workers.x_sender_pw_worker import XSenderPWWorker as XSenderWorker
from workers.email_sender_worker import EmailSenderWorker
import db, config
from gui.thread_bridge import enqueue


class SenderTab:
    def __init__(self, parent):
        self.parent   = parent
        self.tg_w     = None
        self.x_w      = None
        self.email_w  = None
        self._build()

    def _build(self):
        ctk.CTkLabel(self.parent, text="发送控制",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(14, 6))

        # 三个发送渠道拆成子 Tab：每个渠道独占屏幕，按钮不会被挤隐藏
        self.sub_tabs = ctk.CTkTabview(self.parent)
        self.sub_tabs.pack(fill="both", expand=True, padx=10, pady=4)

        self._build_tg_panel(self.sub_tabs.add("Telegram"))
        self._build_x_panel(self.sub_tabs.add("X (Twitter)"))
        self._build_email_panel(self.sub_tabs.add("邮件"))

    # ════════════════ TG 发送 ════════════════════════════════
    def _build_tg_panel(self, pane):
        frame = ctk.CTkFrame(pane, fg_color=("gray85", "gray22"))
        frame.pack(fill="both", expand=True, padx=6, pady=6)

        ctk.CTkLabel(frame, text="Telegram 发送",
                     font=ctk.CTkFont(weight="bold")).pack(pady=(10, 4))

        # 数据源选择（动态读 DB distinct source）
        src_row = ctk.CTkFrame(frame, fg_color="transparent")
        src_row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(src_row, text="数据源：", width=60).pack(side="left")
        self.tg_source = ctk.CTkOptionMenu(src_row, values=["all"])
        self.tg_source.pack(side="left", padx=4)
        ctk.CTkButton(src_row, text="🔄", width=28, height=24,
                      fg_color="gray40", hover_color="gray30",
                      command=self._refresh_tg_sources).pack(side="left", padx=2)
        self._refresh_tg_sources()

        # 每小时限额
        rate_row = ctk.CTkFrame(frame, fg_color="transparent")
        rate_row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(rate_row, text="每小时限额：", width=80).pack(side="left")
        self.e_tg_rate = ctk.CTkEntry(rate_row, width=60,
                                      placeholder_text=str(config.TG_MAX_PER_HOUR))
        self.e_tg_rate.pack(side="left", padx=4)

        # 两平台统一：Playwright 浏览器自动化（操作 web.telegram.org）
        ctk.CTkLabel(frame, text="Playwright 模式：连接 Telegram Web 自动发送",
                     text_color="gray").pack(fill="x", padx=14, pady=4)

        # 文案信息
        self.lbl_tg_msg = ctk.CTkLabel(frame, text="激活文案：—",
                                       text_color="gray", anchor="w")
        self.lbl_tg_msg.pack(fill="x", padx=14, pady=2)
        ctk.CTkButton(frame, text="刷新文案", width=80, height=22, fg_color="gray40",
                      command=self._refresh_tg_msg).pack(anchor="w", padx=14, pady=2)
        self._refresh_tg_msg()

        # 日志
        self.tg_log = ctk.CTkTextbox(frame, height=240,
                                     font=ctk.CTkFont(family="Consolas", size=11))
        self.tg_log.pack(fill="both", expand=True, padx=10, pady=4)
        self.tg_log.configure(state="disabled")

        # 按钮
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", pady=6)
        self.btn_tg_start = ctk.CTkButton(btn_row, text="▶ 开始发送",
                                          command=self._start_tg)
        self.btn_tg_start.pack(side="left", padx=4)
        self.btn_tg_stop = ctk.CTkButton(btn_row, text="⏹ 停止",
                                         fg_color="#c0392b", hover_color="#922b21",
                                         state="disabled", command=self._stop_tg)
        self.btn_tg_stop.pack(side="left", padx=4)
        self.btn_tg_ready = ctk.CTkButton(
            btn_row, text="已登录就绪",
            fg_color="#2196F3", hover_color="#1976D2",
            state="disabled", command=self._ready_tg)
        self.btn_tg_ready.pack(side="left", padx=4)

    # ════════════════ X 发送 ════════════════════════════════
    def _build_x_panel(self, pane):
        frame = ctk.CTkFrame(pane, fg_color=("gray85", "gray22"))
        frame.pack(fill="both", expand=True, padx=6, pady=6)

        ctk.CTkLabel(frame, text="X (Twitter) 发送",
                     font=ctk.CTkFont(weight="bold")).pack(pady=(10, 4))

        # 发送目标模式：项目官号 or 关键人
        mode_row = ctk.CTkFrame(frame, fg_color="transparent")
        mode_row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(mode_row, text="发送目标：", width=72).pack(side="left")
        self.x_mode = ctk.CTkOptionMenu(
            mode_row,
            values=["项目官号 (x_links)", "关键人 (x_contacts)"],
            command=self._on_x_mode_change,
            width=180,
        )
        self.x_mode.pack(side="left", padx=4)

        # 数据源选择（x_links 模式）
        self.x_src_row = ctk.CTkFrame(frame, fg_color="transparent")
        self.x_src_row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(self.x_src_row, text="数据源：", width=72).pack(side="left")
        self.x_source = ctk.CTkOptionMenu(self.x_src_row, values=["all"])
        self.x_source.pack(side="left", padx=4)
        ctk.CTkButton(self.x_src_row, text="🔄", width=28, height=24,
                      fg_color="gray40", hover_color="gray30",
                      command=self._refresh_x_sources).pack(side="left", padx=2)
        self._refresh_x_sources()

        # 角色筛选（x_contacts 模式，默认隐藏）
        self.x_role_row = ctk.CTkFrame(frame, fg_color="transparent")
        ctk.CTkLabel(self.x_role_row, text="角色：", width=72).pack(side="left")
        self.x_role = ctk.CTkOptionMenu(self.x_role_row, values=["all"])
        self.x_role.pack(side="left", padx=4)
        ctk.CTkButton(self.x_role_row, text="🔄", width=28, height=24,
                      fg_color="gray40", hover_color="gray30",
                      command=self._refresh_x_roles).pack(side="left", padx=2)

        # 两平台统一：Playwright 浏览器自动化（CDP 连真实 Chrome，DOM 选择器发送）
        ctk.CTkLabel(frame, text="Playwright 模式：连接 CDP Chrome，DOM 自动发送",
                     text_color="gray").pack(fill="x", padx=14, pady=4)

        # 文案信息
        self.lbl_x_msg = ctk.CTkLabel(frame, text="激活文案：—",
                                      text_color="gray", anchor="w")
        self.lbl_x_msg.pack(fill="x", padx=14, pady=2)
        ctk.CTkButton(frame, text="刷新文案", width=80, height=22, fg_color="gray40",
                      command=self._refresh_x_msg).pack(anchor="w", padx=14, pady=2)
        self._refresh_x_msg()

        # 日志
        self.x_log = ctk.CTkTextbox(frame, height=240,
                                    font=ctk.CTkFont(family="Consolas", size=11))
        self.x_log.pack(fill="both", expand=True, padx=10, pady=4)
        self.x_log.configure(state="disabled")

        # 按钮
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", pady=6)
        self.btn_x_start = ctk.CTkButton(btn_row, text="▶ 开始发送",
                                         command=self._start_x)
        self.btn_x_start.pack(side="left", padx=4)
        self.btn_x_pause = ctk.CTkButton(
            btn_row, text="⏸ 暂停",
            fg_color="#e67e22", hover_color="#d35400",
            state="disabled", command=self._pause_x)
        self.btn_x_pause.pack(side="left", padx=4)
        self.btn_x_resume = ctk.CTkButton(
            btn_row, text="▶ 恢复",
            fg_color="#27ae60", hover_color="#1e8449",
            state="disabled", command=self._resume_x)
        self.btn_x_resume.pack(side="left", padx=4)
        self.btn_x_stop = ctk.CTkButton(btn_row, text="⏹ 停止",
                                        fg_color="#c0392b", hover_color="#922b21",
                                        state="disabled", command=self._stop_x)
        self.btn_x_stop.pack(side="left", padx=4)
        self.btn_x_ready = ctk.CTkButton(
            btn_row, text="已登录就绪",
            fg_color="#2196F3", hover_color="#1976D2",
            state="disabled", command=self._ready_x)
        self.btn_x_ready.pack(side="left", padx=4)

    # ─── 工具方法 ─────────────────────────────────────────────
    def _refresh_tg_sources(self):
        tags = db.list_tg_sources()
        values = ["all"] + tags
        current = self.tg_source.get() if hasattr(self, "tg_source") else "all"
        self.tg_source.configure(values=values)
        self.tg_source.set(current if current in values else "all")

    def _refresh_x_sources(self):
        tags = db.list_x_sources()
        values = ["all"] + tags
        current = self.x_source.get() if hasattr(self, "x_source") else "all"
        self.x_source.configure(values=values)
        self.x_source.set(current if current in values else "all")

    def _refresh_x_roles(self):
        roles = db.list_x_contact_roles()
        values = ["all"] + roles
        current = self.x_role.get() if hasattr(self, "x_role") else "all"
        self.x_role.configure(values=values)
        self.x_role.set(current if current in values else "all")

    def _on_x_mode_change(self, choice):
        if choice == "关键人 (x_contacts)":
            self.x_src_row.pack_forget()
            self.x_role_row.pack(fill="x", padx=14, pady=2)
            self._refresh_x_roles()
        else:
            self.x_role_row.pack_forget()
            self.x_src_row.pack(fill="x", padx=14, pady=2)

    def _refresh_tg_msg(self):
        tmpl = db.get_active_template("telegram")
        if tmpl:
            self.lbl_tg_msg.configure(
                text=f"激活文案：{tmpl['name']}（{len(tmpl['content'])} 字符）",
                text_color="#4CAF50"
            )
        else:
            self.lbl_tg_msg.configure(text="激活文案：无（请在「文案」页设置）",
                                      text_color="#F44336")

    def _refresh_x_msg(self):
        tmpl = db.get_active_template("twitter")
        if tmpl:
            self.lbl_x_msg.configure(
                text=f"激活文案：{tmpl['name']}（{len(tmpl['content'])} 字符）",
                text_color="#4CAF50"
            )
        else:
            self.lbl_x_msg.configure(text="激活文案：无（请在「文案」页设置）",
                                     text_color="#F44336")

    # ── TG 发送 ───────────────────────────────────────────────
    def _log_tg(self, msg):
        def _do():
            self.tg_log.configure(state="normal")
            self.tg_log.insert("end", msg + "\n")
            self.tg_log.see("end")
            self.tg_log.configure(state="disabled")
        enqueue(_do)

    def _start_tg(self):
        tmpl = db.get_active_template("telegram")
        if not tmpl:
            messagebox.showwarning("无文案", "请先在「文案」页激活一条 Telegram 文案")
            return

        source = self.tg_source.get() or "all"
        try:
            rate = int(self.e_tg_rate.get() or config.TG_MAX_PER_HOUR)
        except ValueError:
            rate = config.TG_MAX_PER_HOUR

        self.btn_tg_start.configure(state="disabled")
        self.btn_tg_stop.configure(state="normal")
        self.btn_tg_ready.configure(state="normal")
        self.tg_w = TGSenderWorker(
            log_callback=self._log_tg,
            source=source,
            max_per_hour=rate,
            message_name=tmpl["name"],
            message_content=tmpl["content"]
        )
        threading.Thread(target=self._run_tg, daemon=True).start()

    def _run_tg(self):
        self.tg_w.run()
        enqueue(lambda: self.btn_tg_start.configure(state="normal"))
        enqueue(lambda: self.btn_tg_stop.configure(state="disabled"))
        enqueue(lambda: self.btn_tg_ready.configure(state="disabled"))

    def _ready_tg(self):
        if self.tg_w and hasattr(self.tg_w, 'set_ready'):
            self.tg_w.set_ready()
            self.btn_tg_ready.configure(state="disabled")

    def _stop_tg(self):
        if self.tg_w:
            self.tg_w.stop()
        self.btn_tg_stop.configure(state="disabled")

    # ── X 发送 ────────────────────────────────────────────────
    def _log_x(self, msg):
        def _do():
            self.x_log.configure(state="normal")
            self.x_log.insert("end", msg + "\n")
            self.x_log.see("end")
            self.x_log.configure(state="disabled")
        enqueue(_do)

    def _start_x(self):
        tmpl = db.get_active_template("twitter")
        if not tmpl:
            messagebox.showwarning("无文案", "请先在「文案」页激活一条 X 文案")
            return

        mode_sel = self.x_mode.get() if hasattr(self, "x_mode") else "项目官号 (x_links)"
        if "x_contacts" in mode_sel:
            mode = "x_contacts"
            role_sel = self.x_role.get() if hasattr(self, "x_role") else "all"
            role   = None if role_sel == "all" else role_sel
            source = None
        else:
            mode = "x_links"
            role = None
            sel = self.x_source.get() or "all"
            source = None if sel == "all" else sel

        self.btn_x_start.configure(state="disabled")
        self.btn_x_pause.configure(state="normal")
        self.btn_x_resume.configure(state="disabled")
        self.btn_x_stop.configure(state="normal")
        self.btn_x_ready.configure(state="normal")
        self.x_w = XSenderWorker(
            log_callback=self._log_x,
            message_name=tmpl["name"],
            message_content=tmpl["content"],
            source=source,
            mode=mode,
            role=role,
        )
        threading.Thread(target=self._run_x, daemon=True).start()

    def _run_x(self):
        self.x_w.run()
        enqueue(lambda: self.btn_x_start.configure(state="normal"))
        enqueue(lambda: self.btn_x_pause.configure(state="disabled"))
        enqueue(lambda: self.btn_x_resume.configure(state="disabled"))
        enqueue(lambda: self.btn_x_stop.configure(state="disabled"))
        enqueue(lambda: self.btn_x_ready.configure(state="disabled"))

    def _ready_x(self):
        if self.x_w and hasattr(self.x_w, 'set_ready'):
            self.x_w.set_ready()
            self.btn_x_ready.configure(state="disabled")

    def _pause_x(self):
        if self.x_w:
            self.x_w.pause()
        self.btn_x_pause.configure(state="disabled")
        self.btn_x_resume.configure(state="normal")

    def _resume_x(self):
        if self.x_w:
            self.x_w.resume()
        self.btn_x_pause.configure(state="normal")
        self.btn_x_resume.configure(state="disabled")

    def _stop_x(self):
        if self.x_w:
            self.x_w.resume()   # 解除暂停，让 _stop 被检测到
            self.x_w.stop()
        self.btn_x_pause.configure(state="disabled")
        self.btn_x_resume.configure(state="disabled")
        self.btn_x_stop.configure(state="disabled")

    # ════════════════ 邮件发送 ════════════════════════════════
    def _build_email_panel(self, pane):
        frame = ctk.CTkFrame(pane, fg_color=("gray85", "gray22"))
        frame.pack(fill="both", expand=True, padx=6, pady=6)

        ctk.CTkLabel(frame, text="邮件发送",
                     font=ctk.CTkFont(weight="bold")).pack(pady=(10, 4))

        src_row = ctk.CTkFrame(frame, fg_color="transparent")
        src_row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(src_row, text="数据源：", width=60).pack(side="left")
        self.email_source = ctk.CTkOptionMenu(src_row, values=["all"])
        self.email_source.pack(side="left", padx=4)
        ctk.CTkButton(src_row, text="🔄", width=28, height=24,
                      fg_color="gray40", hover_color="gray30",
                      command=self._refresh_email_sources).pack(side="left", padx=2)
        self._refresh_email_sources()

        limit_row = ctk.CTkFrame(frame, fg_color="transparent")
        limit_row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(limit_row, text="每日限额：", width=60).pack(side="left")
        self.e_email_limit = ctk.CTkEntry(limit_row, width=60, placeholder_text="50")
        self.e_email_limit.pack(side="left", padx=4)
        ctk.CTkLabel(limit_row, text="间隔：", width=36).pack(side="left")
        self.e_email_imin = ctk.CTkEntry(limit_row, width=46, placeholder_text="30")
        self.e_email_imin.pack(side="left", padx=2)
        ctk.CTkLabel(limit_row, text="~").pack(side="left")
        self.e_email_imax = ctk.CTkEntry(limit_row, width=46, placeholder_text="60")
        self.e_email_imax.pack(side="left", padx=2)
        ctk.CTkLabel(limit_row, text="秒", width=20).pack(side="left")

        self.lbl_email_msg = ctk.CTkLabel(frame, text="邮件模板：—",
                                          text_color="gray", anchor="w")
        self.lbl_email_msg.pack(fill="x", padx=14, pady=2)
        ctk.CTkButton(frame, text="刷新模板", width=80, height=22, fg_color="gray40",
                      command=self._refresh_email_msg).pack(anchor="w", padx=14, pady=2)
        self._refresh_email_msg()

        self.email_log = ctk.CTkTextbox(frame, height=240,
                                        font=ctk.CTkFont(family="Consolas", size=11))
        self.email_log.pack(fill="both", expand=True, padx=10, pady=4)
        self.email_log.configure(state="disabled")

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", pady=6)
        self.btn_email_start = ctk.CTkButton(btn_row, text="▶ 开始发送",
                                             command=self._start_email)
        self.btn_email_start.pack(side="left", padx=4)
        self.btn_email_stop = ctk.CTkButton(btn_row, text="⏹ 停止",
                                            fg_color="#c0392b", hover_color="#922b21",
                                            state="disabled", command=self._stop_email)
        self.btn_email_stop.pack(side="left", padx=4)

    def _refresh_email_sources(self):
        try:
            tags = db.get_conn().execute(
                "SELECT DISTINCT source FROM emails WHERE source IS NOT NULL"
            ).fetchall()
            values = ["all"] + [r["source"] for r in tags]
        except Exception:
            values = ["all"]
        current = self.email_source.get() if hasattr(self, "email_source") else "all"
        self.email_source.configure(values=values)
        self.email_source.set(current if current in values else "all")

    def _refresh_email_msg(self):
        tmpl = db.get_active_template("email")
        if tmpl:
            lines = tmpl["content"].splitlines()
            subject = lines[0] if lines else ""
            self.lbl_email_msg.configure(
                text=f"邮件模板：{tmpl['name']}  主题：{subject[:30]}",
                text_color="#4CAF50")
        else:
            self.lbl_email_msg.configure(
                text="邮件模板：无（请在「文案」页设置，第一行为主题）",
                text_color="#F44336")

    def _log_email(self, msg):
        def _do():
            self.email_log.configure(state="normal")
            self.email_log.insert("end", msg + "\n")
            self.email_log.see("end")
            self.email_log.configure(state="disabled")
        enqueue(_do)

    def _start_email(self):
        tmpl = db.get_active_template("email")
        if not tmpl:
            messagebox.showwarning("无模板", "请先在「文案」页激活一条邮件模板")
            return
        lines = tmpl["content"].splitlines()
        subject = lines[0].strip() if lines else ""
        body    = "\n".join(lines[1:]).lstrip("\n") if len(lines) > 1 else ""
        if not subject:
            messagebox.showwarning("模板格式", "邮件模板第一行应为邮件主题，当前为空")
            return

        sel = self.email_source.get() or "all"
        source = None if sel == "all" else sel
        try:
            daily_limit = int(self.e_email_limit.get() or 50)
            imin        = int(self.e_email_imin.get()  or 30)
            imax        = int(self.e_email_imax.get()  or 60)
        except ValueError:
            daily_limit, imin, imax = 50, 30, 60

        self.btn_email_start.configure(state="disabled")
        self.btn_email_stop.configure(state="normal")
        self.email_w = EmailSenderWorker(
            log_callback=self._log_email,
            message_name=tmpl["name"],
            subject=subject,
            body=body,
            source=source,
            daily_limit=daily_limit,
            interval_min=imin,
            interval_max=imax,
        )
        threading.Thread(target=self._run_email, daemon=True).start()

    def _run_email(self):
        self.email_w.run()
        enqueue(lambda: self.btn_email_start.configure(state="normal"))
        enqueue(lambda: self.btn_email_stop.configure(state="disabled"))

    def _stop_email(self):
        if self.email_w:
            self.email_w.stop()
        self.btn_email_stop.configure(state="disabled")
