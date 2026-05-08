"""
发送记录标签页 — 触达历史表格 + 筛选
使用 ttk.Treeview 替代 CTkScrollableFrame + CTkLabel，大幅减少 widget 数量。
"""
import customtkinter as ctk
from tkinter import ttk

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db


class HistoryTab:
    def __init__(self, parent):
        self.parent = parent
        self._build()
        self.refresh()

    def _build(self):
        ctk.CTkLabel(self.parent, text="发送记录",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(14, 6))

        # 筛选行
        filter_row = ctk.CTkFrame(self.parent, fg_color="transparent")
        filter_row.pack(fill="x", padx=20, pady=4)

        ctk.CTkLabel(filter_row, text="渠道筛选：", width=70).pack(side="left")
        self.filter_channel = ctk.CTkOptionMenu(
            filter_row,
            values=["all", "telegram", "twitter"],
            command=lambda _: self.refresh()
        )
        self.filter_channel.pack(side="left", padx=6)

        ctk.CTkButton(filter_row, text="🔄 刷新", width=80,
                      command=self.refresh).pack(side="right")

        self.lbl_total = ctk.CTkLabel(filter_row, text="共 0 条", text_color="gray")
        self.lbl_total.pack(side="right", padx=10)

        # ── Treeview 样式 ──────────────────────────────────────
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("History.Treeview",
                        background="#2b2b2b",
                        foreground="white",
                        fieldbackground="#2b2b2b",
                        rowheight=26,
                        font=("Consolas", 11))
        style.configure("History.Treeview.Heading",
                        background="#3a3a3a",
                        foreground="white",
                        font=("", 11, "bold"))
        style.map("History.Treeview",
                  background=[("selected", "#1a5276")])

        # ── Treeview 表格 ──────────────────────────────────────
        columns = ("time", "channel", "handle", "source", "template")
        tree_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=20, pady=(4, 8))

        self.tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings",
            style="History.Treeview", selectmode="browse")

        for cid, text, width in [
            ("time",     "发送时间", 150),
            ("channel",  "渠道",     80),
            ("handle",   "Handle",  180),
            ("source",   "来源",     80),
            ("template", "文案版本", 150),
        ]:
            self.tree.heading(cid, text=text, anchor="w")
            self.tree.column(cid, width=width, anchor="w")

        # 滚动条
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # 渠道颜色 tag
        self.tree.tag_configure("telegram", foreground="#64B5F6")
        self.tree.tag_configure("twitter",  foreground="#FFB74D")

    def refresh(self):
        channel = self.filter_channel.get()
        records = db.get_send_log(channel=channel, limit=300)

        self.tree.delete(*self.tree.get_children())
        self.lbl_total.configure(text=f"共 {len(records)} 条")

        for r in records:
            tag = r["channel"] if r["channel"] in ("telegram", "twitter") else ""
            self.tree.insert("", "end", values=(
                r["sent_at"][:16],
                r["channel"],
                f"@{r['handle']}",
                r["source"],
                r["message_name"],
            ), tags=(tag,))
