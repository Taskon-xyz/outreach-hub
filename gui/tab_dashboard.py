"""
仪表盘标签页 — 总览数字卡片 + 待发队列 + 最近发送
"""
import customtkinter as ctk
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db


class DashboardTab:
    def __init__(self, parent):
        self.parent = parent
        self._build()
        self.refresh()

    def _build(self):
        # ── 标题 ─────────────────────────────────────────────
        ctk.CTkLabel(
            self.parent, text="Web3 Outreach Hub — 仪表盘",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(16, 8))

        # ── 数字卡片行 ────────────────────────────────────────
        card_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        card_frame.pack(fill="x", padx=20, pady=6)

        self.cards = {}
        card_defs = [
            ("projects",      "项目总数"),
            ("tg_links",      "TG 群链接"),
            ("x_links",       "X 账号"),
            ("tg_handles",    "TG 管理员"),
            ("tg_left_users", "离群用户"),
            ("sent_total",    "累计发送"),
        ]
        for i, (key, label) in enumerate(card_defs):
            card = ctk.CTkFrame(card_frame, fg_color=("gray80", "gray25"), corner_radius=10)
            card.grid(row=0, column=i, padx=6, pady=4, sticky="nsew")
            card_frame.columnconfigure(i, weight=1)

            num_lbl = ctk.CTkLabel(card, text="0",
                                   font=ctk.CTkFont(size=24, weight="bold"),
                                   text_color="#4CAF50")
            num_lbl.pack(pady=(10, 2))
            ctk.CTkLabel(card, text=label, text_color="gray").pack(pady=(0, 10))
            self.cards[key] = num_lbl

        # ── 待发队列 ──────────────────────────────────────────
        queue_frame = ctk.CTkFrame(self.parent, fg_color=("gray85", "gray20"))
        queue_frame.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(queue_frame, text="待发队列",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=14, pady=(8, 4))

        self.lbl_tg_pending = ctk.CTkLabel(queue_frame, text="TG 待发：—", anchor="w")
        self.lbl_tg_pending.pack(anchor="w", padx=20, pady=2)
        self.lbl_x_pending = ctk.CTkLabel(queue_frame, text="X 待发：—", anchor="w")
        self.lbl_x_pending.pack(anchor="w", padx=20, pady=(2, 8))

        # ── 最近发送 ──────────────────────────────────────────
        ctk.CTkLabel(self.parent, text="最近发送（10条）",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=24, pady=(6, 2))

        self.log_box = ctk.CTkTextbox(
            self.parent, height=180,
            font=ctk.CTkFont(family="Consolas", size=12)
        )
        self.log_box.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        self.log_box.configure(state="disabled")

        # ── 刷新按钮 ──────────────────────────────────────────
        ctk.CTkButton(self.parent, text="🔄 刷新", width=100,
                      command=self.refresh).pack(pady=4)

    def refresh(self):
        stats = db.get_stats()
        for key, lbl in self.cards.items():
            lbl.configure(text=str(stats.get(key, 0)))

        self.lbl_tg_pending.configure(text=f"TG 待发：{stats.get('tg_pending', 0)}")
        self.lbl_x_pending.configure(text=f"X 待发：{stats.get('x_pending', 0)}")

        # 最近发送记录
        records = db.get_send_log(limit=10)
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        for r in records:
            self.log_box.insert(
                "end",
                f"{r['sent_at'][:16]}  {r['channel']:9s}  @{r['handle']:20s}  [{r['message_name']}]\n"
            )
        self.log_box.configure(state="disabled")
