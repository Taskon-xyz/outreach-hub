"""
发送标签页 — TG 发送控制 + X 发送控制
坐标校准已移至「⚙️ 设置」页
"""
import threading
import customtkinter as ctk
from tkinter import messagebox

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.tg_sender_worker import TGSenderWorker
if sys.platform == 'darwin':
    from workers.x_sender_pw_worker import XSenderPWWorker as XSenderWorker
else:
    from workers.x_sender_worker  import XSenderWorker
import db, config


class SenderTab:
    def __init__(self, parent):
        self.parent   = parent
        self.tg_w     = None
        self.x_w      = None
        self._build()

    def _build(self):
        ctk.CTkLabel(self.parent, text="发送控制",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(14, 6))

        pane = ctk.CTkFrame(self.parent, fg_color="transparent")
        pane.pack(fill="both", expand=True, padx=10, pady=4)
        pane.columnconfigure(0, weight=1)
        pane.columnconfigure(1, weight=1)

        self._build_tg_panel(pane)
        self._build_x_panel(pane)

    # ════════════════ TG 发送 ════════════════════════════════
    def _build_tg_panel(self, pane):
        frame = ctk.CTkFrame(pane, fg_color=("gray85", "gray22"))
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        frame.rowconfigure(4, weight=1)

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
        btn_row.pack(pady=6)
        self.btn_tg_start = ctk.CTkButton(btn_row, text="▶ 开始发送",
                                          command=self._start_tg)
        self.btn_tg_start.pack(side="left", padx=4)
        self.btn_tg_stop = ctk.CTkButton(btn_row, text="⏹ 停止",
                                         fg_color="#c0392b", hover_color="#922b21",
                                         state="disabled", command=self._stop_tg)
        self.btn_tg_stop.pack(side="left", padx=4)

    # ════════════════ X 发送 ════════════════════════════════
    def _build_x_panel(self, pane):
        frame = ctk.CTkFrame(pane, fg_color=("gray85", "gray22"))
        frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        frame.rowconfigure(4, weight=1)

        ctk.CTkLabel(frame, text="X (Twitter) 发送",
                     font=ctk.CTkFont(weight="bold")).pack(pady=(10, 4))

        # 数据源选择（动态读 DB distinct source）
        src_row = ctk.CTkFrame(frame, fg_color="transparent")
        src_row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(src_row, text="数据源：", width=60).pack(side="left")
        self.x_source = ctk.CTkOptionMenu(src_row, values=["all"])
        self.x_source.pack(side="left", padx=4)
        ctk.CTkButton(src_row, text="🔄", width=28, height=24,
                      fg_color="gray40", hover_color="gray30",
                      command=self._refresh_x_sources).pack(side="left", padx=2)
        self._refresh_x_sources()

        # 坐标状态显示 / macOS Playwright 提示
        if sys.platform == 'darwin':
            ctk.CTkLabel(frame, text="macOS 模式：Playwright 浏览器自动化",
                         text_color="gray").pack(fill="x", padx=14, pady=4)
        else:
            coord_card = ctk.CTkFrame(frame, fg_color=("gray80", "gray30"))
            coord_card.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(coord_card, text="已保存坐标",
                         font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=12, pady=(6, 2))
            self.lbl_dm_pos   = ctk.CTkLabel(coord_card, text="DM 按钮：未校准", text_color="gray")
            self.lbl_dm_pos.pack(anchor="w", padx=12)
            self.lbl_chat_pos = ctk.CTkLabel(coord_card, text="消息输入框：未校准", text_color="gray")
            self.lbl_chat_pos.pack(anchor="w", padx=12, pady=(0, 4))
            ctk.CTkLabel(coord_card, text="坐标校准请前往「⚙️ 设置」页",
                         text_color="gray", font=ctk.CTkFont(size=11)).pack(
                             anchor="w", padx=12, pady=(0, 6))
            self._refresh_pos_labels()

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
        btn_row.pack(pady=6)
        self.btn_x_start = ctk.CTkButton(btn_row, text="▶ 开始发送",
                                         command=self._start_x)
        self.btn_x_start.pack(side="left", padx=4)
        self.btn_x_stop = ctk.CTkButton(btn_row, text="⏹ 停止",
                                        fg_color="#c0392b", hover_color="#922b21",
                                        state="disabled", command=self._stop_x)
        self.btn_x_stop.pack(side="left", padx=4)
        if sys.platform == 'darwin':
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

    def _refresh_pos_labels(self):
        try:
            x, y = open(config.DM_POS_FILE).read().strip().split(',')
            self.lbl_dm_pos.configure(text=f"DM 按钮：({x}, {y})", text_color="#4CAF50")
        except Exception:
            self.lbl_dm_pos.configure(text="DM 按钮：未校准", text_color="gray")
        try:
            x, y = open(config.CHAT_POS_FILE).read().strip().split(',')
            self.lbl_chat_pos.configure(text=f"消息输入框：({x}, {y})", text_color="#4CAF50")
        except Exception:
            self.lbl_chat_pos.configure(text="消息输入框：未校准", text_color="gray")

    # ── TG 发送 ───────────────────────────────────────────────
    def _log_tg(self, msg):
        self.tg_log.configure(state="normal")
        self.tg_log.insert("end", msg + "\n")
        self.tg_log.see("end")
        self.tg_log.configure(state="disabled")

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
        self.btn_tg_start.configure(state="normal")
        self.btn_tg_stop.configure(state="disabled")

    def _stop_tg(self):
        if self.tg_w:
            self.tg_w.stop()
        self.btn_tg_stop.configure(state="disabled")

    # ── X 发送 ────────────────────────────────────────────────
    def _log_x(self, msg):
        self.x_log.configure(state="normal")
        self.x_log.insert("end", msg + "\n")
        self.x_log.see("end")
        self.x_log.configure(state="disabled")

    def _start_x(self):
        tmpl = db.get_active_template("twitter")
        if not tmpl:
            messagebox.showwarning("无文案", "请先在「文案」页激活一条 X 文案")
            return
        if sys.platform != 'darwin':
            if not os.path.exists(config.DM_POS_FILE) or not os.path.exists(config.CHAT_POS_FILE):
                messagebox.showwarning("未校准", "请先在「⚙️ 设置」页完成坐标校准")
                return

        sel = self.x_source.get() or "all"
        source = None if sel == "all" else sel

        self.btn_x_start.configure(state="disabled")
        self.btn_x_stop.configure(state="normal")
        if sys.platform == 'darwin' and hasattr(self, 'btn_x_ready'):
            self.btn_x_ready.configure(state="normal")
        self.x_w = XSenderWorker(
            log_callback=self._log_x,
            message_name=tmpl["name"],
            message_content=tmpl["content"],
            source=source,
        )
        threading.Thread(target=self._run_x, daemon=True).start()

    def _run_x(self):
        self.x_w.run()
        self.btn_x_start.configure(state="normal")
        self.btn_x_stop.configure(state="disabled")
        if sys.platform == 'darwin' and hasattr(self, 'btn_x_ready'):
            self.btn_x_ready.configure(state="disabled")

    def _ready_x(self):
        if self.x_w and hasattr(self.x_w, 'set_ready'):
            self.x_w.set_ready()
            self.btn_x_ready.configure(state="disabled")

    def _stop_x(self):
        if self.x_w:
            self.x_w.stop()
        self.btn_x_stop.configure(state="disabled")
