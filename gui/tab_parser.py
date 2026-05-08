"""
解析标签页 — TG 管理员解析 + 离群用户扫描
"""
import threading
import customtkinter as ctk

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.parser_worker  import ParserWorker
from workers.tgleft_worker  import TGLeftWorker
import config


class ParserTab:
    def __init__(self, parent):
        self.parent       = parent
        self.parser_w     = None
        self.tgleft_w     = None
        self._build()

    def _build(self):
        ctk.CTkLabel(self.parent, text="TG 解析",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(14, 6))

        pane = ctk.CTkFrame(self.parent, fg_color="transparent")
        pane.pack(fill="both", expand=True, padx=10, pady=4)
        pane.columnconfigure(0, weight=1)
        pane.columnconfigure(1, weight=1)

        # ── 左：TG 管理员 ────────────────────────────────────
        left = ctk.CTkFrame(pane, fg_color=("gray85", "gray22"))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        ctk.CTkLabel(left, text="TG 管理员解析",
                     font=ctk.CTkFont(weight="bold")).pack(pady=(10, 4))
        ctk.CTkLabel(left,
                     text="进入数据库中所有 TG 群\n提取 Owner / Admin，退群",
                     text_color="gray", justify="center").pack(pady=2)

        self.parser_prog = ctk.CTkProgressBar(left)
        self.parser_prog.pack(fill="x", padx=14, pady=4)
        self.parser_prog.set(0)
        self.lbl_parser_prog = ctk.CTkLabel(left, text="", text_color="gray")
        self.lbl_parser_prog.pack()

        self.parser_log = ctk.CTkTextbox(left, height=260,
                                         font=ctk.CTkFont(family="Consolas", size=11))
        self.parser_log.pack(fill="both", expand=True, padx=10, pady=4)
        self.parser_log.configure(state="disabled")

        pb_row = ctk.CTkFrame(left, fg_color="transparent")
        pb_row.pack(pady=6)
        self.btn_parser_start = ctk.CTkButton(pb_row, text="▶ 开始",
                                              command=self._start_parser)
        self.btn_parser_start.pack(side="left", padx=4)
        self.btn_parser_stop = ctk.CTkButton(pb_row, text="⏹ 停止",
                                             fg_color="#c0392b", hover_color="#922b21",
                                             state="disabled",
                                             command=self._stop_parser)
        self.btn_parser_stop.pack(side="left", padx=4)

        # ── 右：离群用户扫描 ──────────────────────────────────
        right = ctk.CTkFrame(pane, fg_color=("gray85", "gray22"))
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        ctk.CTkLabel(right, text="离群用户扫描",
                     font=ctk.CTkFont(weight="bold")).pack(pady=(10, 4))
        ctk.CTkLabel(right,
                     text="扫描账号所在小群\n找出曾发过言但已离群的用户",
                     text_color="gray", justify="center").pack(pady=2)

        # 参数
        param_row = ctk.CTkFrame(right, fg_color="transparent")
        param_row.pack(pady=4)
        ctk.CTkLabel(param_row, text="最大成员数：", width=90).pack(side="left")
        self.e_max_members = ctk.CTkEntry(param_row, width=60,
                                          placeholder_text=str(config.TGLEFT_MAX_MEMBERS))
        self.e_max_members.pack(side="left", padx=4)
        ctk.CTkLabel(param_row, text="最大消息数：", width=90).pack(side="left")
        self.e_max_messages = ctk.CTkEntry(param_row, width=60,
                                           placeholder_text=str(config.TGLEFT_MAX_MESSAGES))
        self.e_max_messages.pack(side="left", padx=4)

        self.tgleft_log = ctk.CTkTextbox(right, height=260,
                                         font=ctk.CTkFont(family="Consolas", size=11))
        self.tgleft_log.pack(fill="both", expand=True, padx=10, pady=4)
        self.tgleft_log.configure(state="disabled")

        tg_row = ctk.CTkFrame(right, fg_color="transparent")
        tg_row.pack(pady=6)
        self.btn_tgleft_start = ctk.CTkButton(tg_row, text="▶ 开始",
                                              command=self._start_tgleft)
        self.btn_tgleft_start.pack(side="left", padx=4)
        self.btn_tgleft_stop = ctk.CTkButton(tg_row, text="⏹ 停止",
                                             fg_color="#c0392b", hover_color="#922b21",
                                             state="disabled",
                                             command=self._stop_tgleft)
        self.btn_tgleft_stop.pack(side="left", padx=4)

    # ── TG 管理员 ─────────────────────────────────────────────
    def _log_parser(self, msg):
        self.parser_log.configure(state="normal")
        self.parser_log.insert("end", msg + "\n")
        self.parser_log.see("end")
        self.parser_log.configure(state="disabled")

    def _upd_parser(self, cur, total):
        self.parser_prog.set(cur / total if total else 0)
        self.lbl_parser_prog.configure(text=f"{cur}/{total}")

    def _start_parser(self):
        self.btn_parser_start.configure(state="disabled")
        self.btn_parser_stop.configure(state="normal")
        self.parser_w = ParserWorker(self._log_parser, self._upd_parser)
        threading.Thread(target=self._run_parser, daemon=True).start()

    def _run_parser(self):
        self.parser_w.run()
        self.btn_parser_start.configure(state="normal")
        self.btn_parser_stop.configure(state="disabled")

    def _stop_parser(self):
        if self.parser_w:
            self.parser_w.stop()
        self.btn_parser_stop.configure(state="disabled")

    # ── 离群用户 ──────────────────────────────────────────────
    def _log_tgleft(self, msg):
        self.tgleft_log.configure(state="normal")
        self.tgleft_log.insert("end", msg + "\n")
        self.tgleft_log.see("end")
        self.tgleft_log.configure(state="disabled")

    def _start_tgleft(self):
        try:
            max_m = int(self.e_max_members.get()  or config.TGLEFT_MAX_MEMBERS)
            max_msg = int(self.e_max_messages.get() or config.TGLEFT_MAX_MESSAGES)
        except ValueError:
            max_m   = config.TGLEFT_MAX_MEMBERS
            max_msg = config.TGLEFT_MAX_MESSAGES

        self.btn_tgleft_start.configure(state="disabled")
        self.btn_tgleft_stop.configure(state="normal")
        self.tgleft_w = TGLeftWorker(
            log_callback=self._log_tgleft,
            max_members=max_m,
            max_messages=max_msg
        )
        threading.Thread(target=self._run_tgleft, daemon=True).start()

    def _run_tgleft(self):
        self.tgleft_w.run()
        self.btn_tgleft_start.configure(state="normal")
        self.btn_tgleft_stop.configure(state="disabled")

    def _stop_tgleft(self):
        if self.tgleft_w:
            self.tgleft_w.stop()
        self.btn_tgleft_stop.configure(state="disabled")
