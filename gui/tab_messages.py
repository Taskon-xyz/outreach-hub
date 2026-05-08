"""
文案管理标签页 — TG / X 多版本文案编辑
"""
import customtkinter as ctk
from tkinter import messagebox

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db


class MessagesTab:
    def __init__(self, parent):
        self.parent = parent
        self._build()

    def _build(self):
        ctk.CTkLabel(self.parent, text="文案管理",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(14, 6))

        pane = ctk.CTkFrame(self.parent, fg_color="transparent")
        pane.pack(fill="both", expand=True, padx=10)
        pane.columnconfigure(0, weight=1)
        pane.columnconfigure(1, weight=1)

        self._make_channel_panel(pane, "telegram", 0, "Telegram 文案")
        self._make_channel_panel(pane, "twitter",  1, "X (Twitter) 文案")

    def _make_channel_panel(self, parent, channel, col, title):
        frame = ctk.CTkFrame(parent, fg_color=("gray85", "gray22"))
        frame.grid(row=0, column=col, sticky="nsew", padx=5)
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text=title,
                     font=ctk.CTkFont(weight="bold")).grid(
                         row=0, column=0, columnspan=2, pady=(10, 4))

        # 文案列表
        list_frame = ctk.CTkScrollableFrame(frame, height=140)
        list_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=4)

        # 编辑区
        ctk.CTkLabel(frame, text="编辑内容：", anchor="w").grid(
            row=2, column=0, sticky="w", padx=12, pady=(4, 0))
        textbox = ctk.CTkTextbox(frame, height=200,
                                 font=ctk.CTkFont(family="Consolas", size=12))
        textbox.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=10, pady=4)
        frame.rowconfigure(3, weight=1)

        # 名称输入
        name_row = ctk.CTkFrame(frame, fg_color="transparent")
        name_row.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=2)
        ctk.CTkLabel(name_row, text="版本名称：", width=70).pack(side="left")
        name_entry = ctk.CTkEntry(name_row, width=160, placeholder_text="如：冷启动v1")
        name_entry.pack(side="left", padx=4)

        # 按钮
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.grid(row=5, column=0, columnspan=2, pady=6)

        # 用 closure 绑定 channel
        ch = channel
        lf = list_frame

        def refresh_list():
            for w in lf.winfo_children():
                w.destroy()
            templates = db.get_templates(ch)
            for t in templates:
                row_f = ctk.CTkFrame(lf, fg_color="transparent")
                row_f.pack(fill="x", pady=1)
                star = "★" if t["is_active"] else "☆"
                lbl = ctk.CTkLabel(
                    row_f, text=f"{star} {t['name']}",
                    anchor="w", width=200
                )
                lbl.pack(side="left")

                def _load(t=t):
                    textbox.delete("1.0", "end")
                    textbox.insert("1.0", t["content"])
                    name_entry.delete(0, "end")
                    name_entry.insert(0, t["name"])

                def _activate(t=t):
                    db.set_active_template(ch, t["name"])
                    refresh_list()

                def _delete(t=t):
                    if messagebox.askyesno("确认", f"删除「{t['name']}」？"):
                        db.delete_template(t["id"])
                        refresh_list()

                ctk.CTkButton(row_f, text="加载", width=44, height=22,
                              command=_load).pack(side="left", padx=2)
                ctk.CTkButton(row_f, text="激活", width=44, height=22,
                              fg_color="gray40", command=_activate).pack(side="left", padx=2)
                ctk.CTkButton(row_f, text="删除", width=44, height=22,
                              fg_color="#c0392b", hover_color="#922b21",
                              command=_delete).pack(side="left", padx=2)

        def save():
            name    = name_entry.get().strip()
            content = textbox.get("1.0", "end").strip()
            if not name or not content:
                messagebox.showwarning("提示", "版本名称和内容不能为空")
                return
            db.save_template(ch, name, content)
            refresh_list()
            messagebox.showinfo("已保存", f"「{name}」已保存")

        def new():
            name_entry.delete(0, "end")
            textbox.delete("1.0", "end")

        ctk.CTkButton(btn_row, text="💾 保存", width=70, command=save).pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text="＋ 新建", width=70, fg_color="gray40",
                      command=new).pack(side="left", padx=4)

        refresh_list()
