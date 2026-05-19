"""
爬虫标签页
左：数据源（左侧导航卡片列表）
右：选中数据源的操作面板
"""
import threading
import customtkinter as ctk

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.scraper_worker              import ScraperWorker
from workers.crunchbase_discover_worker  import CrunchbaseDiscoverWorker
from workers.rootdata_worker             import RootDataWorker
from workers.chainscope_worker           import ChainScopeWorker
from workers.token_finder_worker         import TokenFinderWorker
from workers.campaign_worker             import CampaignWorker
from workers.cryptorank_worker           import CryptoRankWorker
from workers.x_profile_search_worker     import XProfileSearchWorker
import db
from gui.thread_bridge import enqueue


class SourceTagSelector(ctk.CTkFrame):
    """下拉选择已有 source tag / 选"其他"后切换为文本框输入新 tag"""
    def __init__(self, parent, placeholder_text="必填", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.columnconfigure(0, weight=1)

        tags = db.get_all_source_tags()
        values = ["请选择..."] + tags + ["其他"]

        self._mode = "combo"
        self._combo = ctk.CTkComboBox(self, values=values, command=self._on_select)
        self._combo.grid(row=0, column=0, sticky="ew")

        self._entry = ctk.CTkEntry(self, placeholder_text=placeholder_text)

    def _on_select(self, choice):
        if choice != "其他":
            return
        self._combo.grid_remove()
        self._entry.grid(row=0, column=0, sticky="ew")
        self._mode = "entry"
        self._entry.focus()

    def get(self):
        if self._mode == "entry":
            return self._entry.get().strip()
        val = self._combo.get()
        return "" if val in ("请选择...", "其他") else val.strip()

    def set(self, value):
        if self._mode == "entry":
            self._entry.delete(0, "end")
            self._entry.insert(0, value)
        else:
            self._combo.set(value)

    def refresh_tags(self):
        """刷新下拉列表（例如运行完成后可能有新 tag）"""
        tags = db.get_all_source_tags()
        values = ["请选择..."] + tags + ["其他"]
        self._combo.configure(values=values)


# ── 数据源定义 ──────────────────────────────────────────────────────────────
SOURCES = [
    {
        "id": "sc",
        "name": "官网 → TG + X",
        "sub":  "扫描数据库中未爬官网",
        "panel": "_build_sc_inner_panel",
    },
    {
        "id": "cb",
        "name": "Crunchbase → 官网",
        "sub":  "逐页爬取公司官网",
        "panel": "_build_cb_panel",
    },
    {
        "id": "rd",
        "name": "RootData → 官网+TG+X",
        "sub":  "Fundraising 列表直接入库",
        "panel": "_build_rd_panel",
    },
    {
        "id": "cs",
        "name": "Old汤-链上变化",
        "sub":  "官网 + Twitter",
        "panel": "_build_cs_panel",
    },
    {
        "id": "tf",
        "name": "Old汤-低交易量",
        "sub":  "仅 Twitter 账号",
        "panel": "_build_tf_panel",
    },
    {
        "id": "ct",
        "name": "活动项目-Twitter",
        "sub":  "twitter_handle 字段",
        "panel": "_build_ct_panel",
    },
    {
        "id": "ck",
        "name": "活动项目-KOL",
        "sub":  "project_handle 字段",
        "panel": "_build_ck_panel",
    },
    {
        "id": "cr",
        "name": "CryptoRank → 官网+X+TG",
        "sub":  "Funding Rounds 列表",
        "panel": "_build_cr_panel",
    },
    {
        "id": "xps",
        "name": "X 关键人搜索",
        "sub":  "CEO/CMO/Growth → x_contacts",
        "panel": "_build_xps_panel",
    },
]

# 每个面板的 panel frame（由 _build_all_panels 创建后填充到右侧）
_panel_frames = {}
_active_id = None


class ScraperTab:
    def __init__(self, parent):
        self.parent     = parent
        self.cb_worker  = None
        self.rd_worker  = None
        self.cr_worker  = None
        self.sc_worker  = None
        self.cs_worker  = None
        self.tf_worker  = None
        self.xps_worker = None
        self._cb_login_event = threading.Event()
        self.var_use_llm = None   # 初始化，避免 _sc_start 访问时异常
        self._build()

    def _build(self):
        # 主标题填满宽度
        ctk.CTkLabel(self.parent, text="爬虫",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(
                         padx=10, pady=(14, 4))

        # ── 左右分栏 ────────────────────────────────────────────────
        main = ctk.CTkFrame(self.parent, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        main.columnconfigure(0, weight=0)   # 左侧导航，固定 210px
        main.columnconfigure(1, weight=1)    # 右侧填满剩余空间

        # ── 左侧：导航卡片列表（固定宽度，不缩放）──────────────────
        nav = ctk.CTkFrame(main, fg_color=("gray85", "gray22"), corner_radius=8)
        nav.configure(width=210)
        nav.grid(row=0, column=0, sticky="ns", padx=(0, 6))
        nav.grid_propagate(False)   # 固定宽度，防止按钮撑大

        ctk.CTkLabel(
            nav, text="数据源",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="gray"
        ).pack(pady=(10, 2))

        self._nav_buttons = {}
        self._nav_frames = {}
        for src in SOURCES:
            item = ctk.CTkFrame(nav, fg_color="transparent", corner_radius=6)
            item.pack(fill="x", padx=6, pady=2)

            btn = ctk.CTkButton(
                item, text=src["name"],
                fg_color=("gray70", "gray30"),
                hover_color=("#4a4a6a", "#3a3a5a"),
                text_color=("gray10", "gray90"),
                anchor="w",
                height=36,
                corner_radius=6,
                font=ctk.CTkFont(size=12),
                command=lambda s=src: self._select_source(s),
            )
            btn.pack(fill="x")
            ctk.CTkLabel(
                item, text=src["sub"],
                text_color="gray", anchor="w",
                font=ctk.CTkFont(size=10),
            ).pack(anchor="w", padx=12, pady=(0, 2))

            self._nav_buttons[src["id"]] = btn
            self._nav_frames[src["id"]] = item

        # ── 右侧：操作面板容器 ─────────────────────────────────────────
        self._right_frame = ctk.CTkFrame(main, fg_color=("gray85", "gray22"), corner_radius=8)
        self._right_frame.grid(row=0, column=1, sticky="nsew")
        self._right_frame.columnconfigure(0, weight=1)
        self._right_frame.rowconfigure(0, weight=1)

        # 每个数据源的面板 frame 直接作为 _right_frame 的子级，
        # 都放在 row=0, column=0（互相重叠）。_right_frame 始终有一个面板
        # 可见，所以 geometry 始终正确分配。切换时用 grid_remove() / grid()。
        for src in SOURCES:
            f = ctk.CTkFrame(self._right_frame, fg_color="transparent")
            f.grid(row=0, column=0, sticky="nsew")
            _panel_frames[src["id"]] = f
            f.grid_remove()   # 初始全部隐藏

        # 构建各面板内容
        self._build_sc_inner_panel(_panel_frames["sc"])
        self._build_cb_panel(_panel_frames["cb"])
        self._build_rd_panel(_panel_frames["rd"])
        self._build_cs_panel(_panel_frames["cs"])
        self._build_tf_panel(_panel_frames["tf"])
        self._build_ct_panel(_panel_frames["ct"])
        self._build_ck_panel(_panel_frames["ck"])
        self._build_cr_panel(_panel_frames["cr"])
        self._build_xps_panel(_panel_frames["xps"])

        # 默认选中第一个（官网爬虫，最核心）
        self._select_source(SOURCES[0])

    def _refresh_all_tag_selectors(self):
        """运行完成后刷新所有 source tag 下拉列表"""
        for attr in ("cb_tag_entry", "rd_tag_entry", "cs_tag_entry",
                     "tf_tag_entry", "ct_tag_entry", "ck_tag_entry", "cr_tag_entry"):
            widget = getattr(self, attr, None)
            if widget:
                widget.refresh_tags()

    # ── 切换数据源 ────────────────────────────────────────────────────────
    def _select_source(self, src):
        global _active_id
        _active_id = src["id"]

        # 高亮当前按钮
        for sid, btn in self._nav_buttons.items():
            if sid == src["id"]:
                btn.configure(
                    fg_color=("#3a5a8a", "#2a4a7a"),
                    text_color=("white", "white"),
                )
            else:
                btn.configure(
                    fg_color=("gray70", "gray30"),
                    text_color=("gray10", "gray90"),
                )

        # 切换右侧面板
        for sid, f in _panel_frames.items():
            if sid == src["id"]:
                f.grid()   # 显示（恢复之前的 grid 布局）
            else:
                f.grid_remove()   # 隐藏（比 pack_forget 更干净）

    # ════════════════ 官网 → TG + X 链接（官网爬虫面板）═══════════════
    def _build_sc_inner_panel(self, parent):
        """官网 → TG + X 链接，独立面板"""
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(parent, text="官网 → TG + X 链接",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(10, 4))
        ctk.CTkLabel(
            parent,
            text="逐一扫描数据库中未解析的官网，提取 Telegram 群链接和 X 账号。",
            text_color="gray", wraplength=400, justify="left"
        ).pack(anchor="w", padx=14, pady=(0, 6))

        self.sc_lbl_count = ctk.CTkLabel(parent, text="", text_color="#4CAF50")
        self.sc_lbl_count.pack(anchor="w", padx=14)
        self._sc_refresh_count()

        self.var_use_llm = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            parent,
            text="发现多个候选时调用 DeepSeek 筛选（需在设置页填写 API Key）",
            variable=self.var_use_llm,
        ).pack(anchor="w", padx=14, pady=(0, 4))

        self.sc_progress = ctk.CTkProgressBar(parent)
        self.sc_progress.pack(fill="x", padx=14, pady=6)
        self.sc_progress.set(0)
        self.sc_lbl_progress = ctk.CTkLabel(parent, text="", text_color="gray")
        self.sc_lbl_progress.pack()

        self.sc_log = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=11))
        self.sc_log.pack(fill="both", expand=True, padx=10, pady=4)
        self.sc_log.configure(state="disabled")

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=6)
        self.sc_btn_start = ctk.CTkButton(btn_row, text="▶ 开始爬取",
                                          command=self._sc_start)
        self.sc_btn_start.pack(side="left", padx=4)
        self.sc_btn_stop = ctk.CTkButton(
            btn_row, text="⏹ 停止",
            fg_color="#c0392b", hover_color="#922b21",
            state="disabled", command=self._sc_stop)
        self.sc_btn_stop.pack(side="left", padx=4)

    # ════════════════ Crunchbase → 官网 ════════════════════════════════
    def _build_cb_panel(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            parent,
            text="从 Crunchbase Discover 列表逐页抓取公司官网，写入数据库。\n"
                 "浏览器打开后手动登录并翻到目标页，再点击「已就位」。",
            text_color="gray", wraplength=400, justify="left"
        ).pack(anchor="w", padx=14, pady=(10, 4))

        url_row = ctk.CTkFrame(parent, fg_color="transparent")
        url_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(url_row, text="列表URL：", width=62, anchor="w").pack(side="left")
        self.cb_url_entry = ctk.CTkEntry(
            url_row, placeholder_text="https://www.crunchbase.com/discover/saved/...")
        self.cb_url_entry.pack(side="left", fill="x", expand=True)

        tag_row = ctk.CTkFrame(parent, fg_color="transparent")
        tag_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(tag_row, text="source tag：", width=62, anchor="w").pack(side="left")
        self.cb_tag_entry = SourceTagSelector(
            tag_row, placeholder_text="必填，如 cb-Q2-defi / batch-2026-04")
        self.cb_tag_entry.pack(side="left", fill="x", expand=True)

        self.cb_lbl_count = ctk.CTkLabel(parent, text="", text_color="#4CAF50")
        self.cb_lbl_count.pack(anchor="w", padx=14)
        self._cb_refresh_count()

        self.cb_progress = ctk.CTkProgressBar(parent)
        self.cb_progress.pack(fill="x", padx=14, pady=4)
        self.cb_progress.set(0)
        self.cb_lbl_progress = ctk.CTkLabel(parent, text="", text_color="gray")
        self.cb_lbl_progress.pack()

        self.cb_log = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=11))
        self.cb_log.pack(fill="both", expand=True, padx=10, pady=4)
        self.cb_log.configure(state="disabled")

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=6)
        self.cb_btn_start = ctk.CTkButton(btn_row, text="▶ 开始",
                                          width=80, command=self._cb_start)
        self.cb_btn_start.pack(side="left", padx=3)
        self.cb_btn_login = ctk.CTkButton(
            btn_row, text="✓ 已就位，开始抓取", width=130,
            fg_color="#2e7d32", hover_color="#1b5e20",
            state="disabled", command=self._cb_login_done)
        self.cb_btn_login.pack(side="left", padx=3)
        self.cb_btn_stop = ctk.CTkButton(
            btn_row, text="⏹ 停止", width=60,
            fg_color="#c0392b", hover_color="#922b21",
            state="disabled", command=self._cb_stop)
        self.cb_btn_stop.pack(side="left", padx=3)

    # ════════════════ RootData → 官网+TG+X ═══════════════════════════
    def _build_rd_panel(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            parent,
            text="从 RootData Fundraising 逐页抓取项目，\n"
                 "直接提取官网 + TG 群链接 + X 账号入库，无需再跑爬虫。",
            text_color="gray", wraplength=400, justify="left"
        ).pack(anchor="w", padx=14, pady=(10, 4))

        url_row = ctk.CTkFrame(parent, fg_color="transparent")
        url_row.pack(fill="x", padx=14, pady=(0, 2))
        ctk.CTkLabel(url_row, text="起始URL：", width=62, anchor="w").pack(side="left")
        self.rd_url_entry = ctk.CTkEntry(
            url_row, placeholder_text="https://www.rootdata.com/fundraising")
        self.rd_url_entry.pack(side="left", fill="x", expand=True)
        self.rd_url_entry.insert(0, "https://www.rootdata.com/fundraising")

        page_row = ctk.CTkFrame(parent, fg_color="transparent")
        page_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(page_row, text="最大页数：", width=62, anchor="w").pack(side="left")
        self.rd_max_pages = ctk.CTkEntry(page_row, width=70, placeholder_text="314")
        self.rd_max_pages.pack(side="left")
        ctk.CTkLabel(page_row, text="  共314页，约9403条",
                     text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left")

        tag_row = ctk.CTkFrame(parent, fg_color="transparent")
        tag_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(tag_row, text="source tag：", width=62, anchor="w").pack(side="left")
        self.rd_tag_entry = SourceTagSelector(
            tag_row, placeholder_text="必填，如 rd-fundraising-2026q2")
        self.rd_tag_entry.pack(side="left", fill="x", expand=True)

        self.rd_lbl_count = ctk.CTkLabel(parent, text="", text_color="#4CAF50")
        self.rd_lbl_count.pack(anchor="w", padx=14)
        self._rd_refresh_count()

        self.rd_progress = ctk.CTkProgressBar(parent)
        self.rd_progress.pack(fill="x", padx=14, pady=4)
        self.rd_progress.set(0)
        self.rd_lbl_progress = ctk.CTkLabel(parent, text="", text_color="gray")
        self.rd_lbl_progress.pack()

        self.rd_log = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=11))
        self.rd_log.pack(fill="both", expand=True, padx=10, pady=4)
        self.rd_log.configure(state="disabled")

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=6)
        self.rd_btn_start = ctk.CTkButton(btn_row, text="▶ 开始",
                                          width=80, command=self._rd_start)
        self.rd_btn_start.pack(side="left", padx=3)
        self.rd_btn_ready = ctk.CTkButton(
            btn_row, text="✓ 已就绪", width=90,
            fg_color="#2e7d32", hover_color="#1b5e20",
            state="disabled", command=self._rd_ready)
        self.rd_btn_ready.pack(side="left", padx=3)
        self.rd_btn_stop = ctk.CTkButton(
            btn_row, text="⏹ 停止", width=60,
            fg_color="#c0392b", hover_color="#922b21",
            state="disabled", command=self._rd_stop)
        self.rd_btn_stop.pack(side="left", padx=3)

    # ════════════════ Old汤-链上变化 ══════════════════════════════════
    def _build_cs_panel(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            parent,
            text="从 Old汤-链上 逐页抓取项目官网和 Twitter，入库 projects + x_links。\n"
                 "纯 API 翻页，相邻两页数据一致则自动停止。",
            text_color="gray", wraplength=400, justify="left"
        ).pack(anchor="w", padx=14, pady=(10, 4))

        tag_row = ctk.CTkFrame(parent, fg_color="transparent")
        tag_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(tag_row, text="source tag：", width=62, anchor="w").pack(side="left")
        self.cs_tag_entry = SourceTagSelector(
            tag_row, placeholder_text="必填，如 chainscope-2026q2")
        self.cs_tag_entry.pack(side="left", fill="x", expand=True)

        self.cs_lbl_count = ctk.CTkLabel(parent, text="", text_color="#4CAF50")
        self.cs_lbl_count.pack(anchor="w", padx=14)
        self._cs_refresh_count()

        self.cs_log = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=11))
        self.cs_log.pack(fill="both", expand=True, padx=10, pady=4)
        self.cs_log.configure(state="disabled")

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=6)
        self.cs_btn_start = ctk.CTkButton(btn_row, text="▶ 开始",
                                          width=80, command=self._cs_start)
        self.cs_btn_start.pack(side="left", padx=3)
        self.cs_btn_stop = ctk.CTkButton(
            btn_row, text="⏹ 停止", width=60,
            fg_color="#c0392b", hover_color="#922b21",
            state="disabled", command=self._cs_stop)
        self.cs_btn_stop.pack(side="left", padx=3)

    # ════════════════ Old汤-低交易量 ══════════════════════════════════
    def _build_tf_panel(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            parent,
            text="从 Old汤-低交易量 逐页抓取 Twitter 账号，写入 x_links 表。\n"
                 "纯 API 翻页，offset += 50 直到拿完全部。",
            text_color="gray", wraplength=400, justify="left"
        ).pack(anchor="w", padx=14, pady=(10, 4))

        tag_row = ctk.CTkFrame(parent, fg_color="transparent")
        tag_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(tag_row, text="source tag：", width=62, anchor="w").pack(side="left")
        self.tf_tag_entry = SourceTagSelector(
            tag_row, placeholder_text="必填，如 tokenfinder-lowvol-2026q2")
        self.tf_tag_entry.pack(side="left", fill="x", expand=True)

        self.tf_lbl_count = ctk.CTkLabel(parent, text="", text_color="#4CAF50")
        self.tf_lbl_count.pack(anchor="w", padx=14)
        self._tf_refresh_count()

        self.tf_log = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=11))
        self.tf_log.pack(fill="both", expand=True, padx=10, pady=4)
        self.tf_log.configure(state="disabled")

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=6)
        self.tf_btn_start = ctk.CTkButton(btn_row, text="▶ 开始",
                                          width=80, command=self._tf_start)
        self.tf_btn_start.pack(side="left", padx=3)
        self.tf_btn_stop = ctk.CTkButton(
            btn_row, text="⏹ 停止", width=60,
            fg_color="#c0392b", hover_color="#922b21",
            state="disabled", command=self._tf_stop)
        self.tf_btn_stop.pack(side="left", padx=3)

    # ════════════════ 活动项目-Twitter ═══════════════════════════════
    def _build_ct_panel(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            parent,
            text="从活动项目列表抓取，字段 twitter_handle（带 @ 需去掉）。\n"
                 "翻页直到拿完全部。",
            text_color="gray", wraplength=400, justify="left"
        ).pack(anchor="w", padx=14, pady=(10, 4))

        tag_row = ctk.CTkFrame(parent, fg_color="transparent")
        tag_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(tag_row, text="source tag：", width=62, anchor="w").pack(side="left")
        self.ct_tag_entry = SourceTagSelector(
            tag_row, placeholder_text="必填，如 campaign-twitter-2026q2")
        self.ct_tag_entry.pack(side="left", fill="x", expand=True)

        self.ct_lbl_count = ctk.CTkLabel(parent, text="", text_color="#4CAF50")
        self.ct_lbl_count.pack(anchor="w", padx=14)
        self._ct_refresh_count()

        self.ct_log = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=11))
        self.ct_log.pack(fill="both", expand=True, padx=10, pady=4)
        self.ct_log.configure(state="disabled")

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=6)
        self.ct_btn_start = ctk.CTkButton(btn_row, text="▶ 开始",
                                          width=80, command=self._ct_start)
        self.ct_btn_start.pack(side="left", padx=3)
        self.ct_btn_stop = ctk.CTkButton(
            btn_row, text="⏹ 停止", width=60,
            fg_color="#c0392b", hover_color="#922b21",
            state="disabled", command=self._ct_stop)
        self.ct_btn_stop.pack(side="left", padx=3)

    # ════════════════ 活动项目-KOL ══════════════════════════════════
    def _build_ck_panel(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            parent,
            text="从活动项目 KOL 列表抓取，字段 project_handle（无 @ 前缀）。\n"
                 "翻页直到拿完全部。",
            text_color="gray", wraplength=400, justify="left"
        ).pack(anchor="w", padx=14, pady=(10, 4))

        tag_row = ctk.CTkFrame(parent, fg_color="transparent")
        tag_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(tag_row, text="source tag：", width=62, anchor="w").pack(side="left")
        self.ck_tag_entry = SourceTagSelector(
            tag_row, placeholder_text="必填，如 campaign-kol-2026q2")
        self.ck_tag_entry.pack(side="left", fill="x", expand=True)

        self.ck_lbl_count = ctk.CTkLabel(parent, text="", text_color="#4CAF50")
        self.ck_lbl_count.pack(anchor="w", padx=14)
        self._ck_refresh_count()

        self.ck_log = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=11))
        self.ck_log.pack(fill="both", expand=True, padx=10, pady=4)
        self.ck_log.configure(state="disabled")

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=6)
        self.ck_btn_start = ctk.CTkButton(btn_row, text="▶ 开始",
                                          width=80, command=self._ck_start)
        self.ck_btn_start.pack(side="left", padx=3)
        self.ck_btn_stop = ctk.CTkButton(
            btn_row, text="⏹ 停止", width=60,
            fg_color="#c0392b", hover_color="#922b21",
            state="disabled", command=self._ck_stop)
        self.ck_btn_stop.pack(side="left", padx=3)

    # ════════════════ CryptoRank 面板 ════════════════════════════════
    def _build_cr_panel(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            parent,
            text="从 CryptoRank Funding Rounds 逐页抓取项目，\n"
                 "直接提取官网 + X 账号 + TG 群链接入库，无需再跑爬虫。\n"
                 "浏览器打开后可手动导航到任意页，点「已就绪」开始抓取。",
            text_color="gray", wraplength=400, justify="left"
        ).pack(anchor="w", padx=14, pady=(10, 4))

        url_row = ctk.CTkFrame(parent, fg_color="transparent")
        url_row.pack(fill="x", padx=14, pady=(0, 2))
        ctk.CTkLabel(url_row, text="起始URL：", width=62, anchor="w").pack(side="left")
        self.cr_url_entry = ctk.CTkEntry(
            url_row, placeholder_text="https://cryptorank.io/funding-rounds?page=1&rows=20")
        self.cr_url_entry.pack(side="left", fill="x", expand=True)
        self.cr_url_entry.insert(0, "https://cryptorank.io/funding-rounds?page=1&rows=20")

        page_row = ctk.CTkFrame(parent, fg_color="transparent")
        page_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(page_row, text="最大页数：", width=62, anchor="w").pack(side="left")
        self.cr_max_pages = ctk.CTkEntry(page_row, width=70, placeholder_text="999")
        self.cr_max_pages.pack(side="left")

        tag_row = ctk.CTkFrame(parent, fg_color="transparent")
        tag_row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(tag_row, text="source tag：", width=62, anchor="w").pack(side="left")
        self.cr_tag_entry = SourceTagSelector(
            tag_row, placeholder_text="必填，如 cryptorank-2026q2")
        self.cr_tag_entry.pack(side="left", fill="x", expand=True)

        self.cr_lbl_count = ctk.CTkLabel(parent, text="", text_color="#4CAF50")
        self.cr_lbl_count.pack(anchor="w", padx=14)
        self._cr_refresh_count()

        self.cr_log = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=11))
        self.cr_log.pack(fill="both", expand=True, padx=10, pady=4)
        self.cr_log.configure(state="disabled")

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=6)
        self.cr_btn_start = ctk.CTkButton(btn_row, text="▶ 开始",
                                          width=80, command=self._cr_start)
        self.cr_btn_start.pack(side="left", padx=3)
        self.cr_btn_ready = ctk.CTkButton(
            btn_row, text="✓ 已就绪", width=90,
            fg_color="#2e7d32", hover_color="#1b5e20",
            state="disabled", command=self._cr_ready)
        self.cr_btn_ready.pack(side="left", padx=3)
        self.cr_btn_stop = ctk.CTkButton(
            btn_row, text="⏹ 停止", width=60,
            fg_color="#c0392b", hover_color="#922b21",
            state="disabled", command=self._cr_stop)
        self.cr_btn_stop.pack(side="left", padx=3)

    def _cr_log(self, msg):
        def _do():
            self.cr_log.configure(state="normal")
            self.cr_log.insert("end", msg + "\n")
            self.cr_log.see("end")
            self.cr_log.configure(state="disabled")
        enqueue(_do)

    def _cr_refresh_count(self):
        self.cr_lbl_count.configure(text=f"数据库已有项目：{db.count_projects()} 条")

    def _cr_start(self):
        tag = (self.cr_tag_entry.get() or "").strip()
        if not tag:
            self._cr_log("请填写 source tag（必填）")
            return
        if tag == "tg_left":
            self._cr_log("source tag 不能为保留值 'tg_left'")
            return
        url = self.cr_url_entry.get().strip() or "https://cryptorank.io/funding-rounds?page=1&rows=20"
        try:
            max_pages = int(self.cr_max_pages.get() or 999)
        except ValueError:
            max_pages = 999

        self.cr_btn_start.configure(state="disabled")
        self.cr_btn_ready.configure(state="normal")
        self.cr_btn_stop.configure(state="normal")
        self.cr_log.configure(state="normal")
        self.cr_log.delete("1.0", "end")
        self.cr_log.configure(state="disabled")
        self.cr_worker = CryptoRankWorker(
            source_tag=tag,
            log_callback=self._cr_log,
            start_url=url,
            max_pages=max_pages,
        )
        threading.Thread(target=self._cr_run, daemon=True).start()

    def _cr_run(self):
        self.cr_worker.run()
        enqueue(lambda: self.cr_btn_start.configure(state="normal"))
        enqueue(lambda: self.cr_btn_ready.configure(state="disabled"))
        enqueue(lambda: self.cr_btn_stop.configure(state="disabled"))
        enqueue(self._cr_refresh_count)
        enqueue(self._refresh_all_tag_selectors)

    def _cr_ready(self):
        if self.cr_worker:
            self.cr_worker.set_ready()
        self.cr_btn_ready.configure(state="disabled")

    def _cr_stop(self):
        if self.cr_worker:
            self.cr_worker.stop()
        self.cr_btn_stop.configure(state="disabled")

    # ════════════════ Crunchbase 控制 ════════════════════════════════
    def _cb_log(self, msg):
        def _do():
            self.cb_log.configure(state="normal")
            self.cb_log.insert("end", msg + "\n")
            self.cb_log.see("end")
            self.cb_log.configure(state="disabled")
        enqueue(_do)

    def _cb_progress_cb(self, cur, total):
        def _do():
            if total:
                self.cb_progress.set(cur / total)
                self.cb_lbl_progress.configure(text=f"{cur} / {total}")
            else:
                self.cb_lbl_progress.configure(text=str(cur))
        enqueue(_do)

    def _cb_refresh_count(self):
        self.cb_lbl_count.configure(text=f"数据库已有官网：{db.count_projects()} 条")

    def _cb_start(self):
        url = self.cb_url_entry.get().strip()
        if not url:
            self._cb_log("请填写 Crunchbase Discover 列表 URL")
            return
        tag = (self.cb_tag_entry.get() or "").strip()
        if not tag:
            self._cb_log("请填写 source tag（本批次分组标签，必填）")
            return
        if tag == "tg_left":
            self._cb_log("source tag 不能为保留值 'tg_left'")
            return
        self._cb_login_event.clear()
        self.cb_btn_start.configure(state="disabled")
        self.cb_btn_stop.configure(state="normal")
        self.cb_log.configure(state="normal")
        self.cb_log.delete("1.0", "end")
        self.cb_log.configure(state="disabled")
        self.cb_progress.set(0)
        self.cb_worker = CrunchbaseDiscoverWorker(
            start_url=url,
            source_tag=tag,
            log_callback=self._cb_log,
            progress_callback=self._cb_progress_cb,
            login_event=self._cb_login_event,
        )
        threading.Thread(target=self._cb_run, daemon=True).start()

    def _cb_run(self):
        import time; time.sleep(6)
        enqueue(lambda: self.cb_btn_login.configure(state="normal"))
        self._cb_log("浏览器已打开，请在 Crunchbase 中翻到目标起始页，然后点击「已就位，开始抓取」。")
        self.cb_worker.run()
        enqueue(lambda: self.cb_btn_start.configure(state="normal"))
        enqueue(lambda: self.cb_btn_login.configure(state="disabled"))
        enqueue(lambda: self.cb_btn_stop.configure(state="disabled"))
        enqueue(self._cb_refresh_count)
        enqueue(self._cs_refresh_count)
        enqueue(self._sc_refresh_count)
        enqueue(self._refresh_all_tag_selectors)

    def _cb_login_done(self):
        self._cb_login_event.set()
        self.cb_btn_login.configure(state="disabled")
        self._cb_log("已就位，将从浏览器当前所在页面开始抓取...")

    def _cb_stop(self):
        if self.cb_worker:
            self.cb_worker.stop()
        self._cb_login_event.set()
        self._cb_log("停止信号已发送...")
        self.cb_btn_stop.configure(state="disabled")

    # ════════════════ RootData 控制 ══════════════════════════════════
    def _rd_log(self, msg):
        def _do():
            self.rd_log.configure(state="normal")
            self.rd_log.insert("end", msg + "\n")
            self.rd_log.see("end")
            self.rd_log.configure(state="disabled")
        enqueue(_do)

    def _rd_progress_cb(self, cur, total):
        enqueue(lambda: self.rd_lbl_progress.configure(text=str(cur)))

    def _rd_refresh_count(self):
        self.rd_lbl_count.configure(text=f"数据库已有官网：{db.count_projects()} 条")

    def _rd_start(self):
        url = self.rd_url_entry.get().strip() or "https://www.rootdata.com/fundraising"
        try:
            max_pages = int(self.rd_max_pages.get() or 314)
        except ValueError:
            max_pages = 314

        tag = (self.rd_tag_entry.get() or "").strip()
        if not tag:
            self._rd_log("请填写 source tag（本批次分组标签，必填）")
            return
        if tag == "tg_left":
            self._rd_log("source tag 不能为保留值 'tg_left'")
            return

        self.rd_btn_start.configure(state="disabled")
        self.rd_btn_stop.configure(state="normal")
        self.rd_log.configure(state="normal")
        self.rd_log.delete("1.0", "end")
        self.rd_log.configure(state="disabled")
        self.rd_progress.set(0)

        self.rd_worker = RootDataWorker(
            source_tag=tag,
            log_callback=self._rd_log,
            progress_callback=self._rd_progress_cb,
            start_url=url,
            max_pages=max_pages,
        )
        threading.Thread(target=self._rd_run, daemon=True).start()

    def _rd_run(self):
        import time; time.sleep(5)
        enqueue(lambda: self.rd_btn_ready.configure(state="normal"))
        self.rd_worker.run()
        enqueue(lambda: self.rd_btn_start.configure(state="normal"))
        enqueue(lambda: self.rd_btn_ready.configure(state="disabled"))
        enqueue(lambda: self.rd_btn_stop.configure(state="disabled"))
        enqueue(self._rd_refresh_count)
        enqueue(self._cs_refresh_count)
        enqueue(self._sc_refresh_count)
        enqueue(self._refresh_all_tag_selectors)

    def _rd_ready(self):
        if self.rd_worker:
            self.rd_worker.set_ready()
        self.rd_btn_ready.configure(state="disabled")

    def _rd_stop(self):
        if self.rd_worker:
            self.rd_worker.stop()
            self.rd_worker.set_ready()
        self._rd_log("停止信号已发送...")
        self.rd_btn_stop.configure(state="disabled")

    # ════════════════ Old汤-链上 控制 ══════════════════════════════════
    def _cs_log(self, msg):
        def _do():
            self.cs_log.configure(state="normal")
            self.cs_log.insert("end", msg + "\n")
            self.cs_log.see("end")
            self.cs_log.configure(state="disabled")
        enqueue(_do)

    def _cs_refresh_count(self):
        self.cs_lbl_count.configure(text=f"数据库已有官网：{db.count_projects()} 条")

    def _cs_start(self):
        tag = (self.cs_tag_entry.get() or "").strip()
        if not tag:
            self._cs_log("请填写 source tag（本批次分组标签，必填）")
            return
        if tag == "tg_left":
            self._cs_log("source tag 不能为保留值 'tg_left'")
            return
        self.cs_btn_start.configure(state="disabled")
        self.cs_btn_stop.configure(state="normal")
        self.cs_log.configure(state="normal")
        self.cs_log.delete("1.0", "end")
        self.cs_log.configure(state="disabled")
        self.cs_worker = ChainScopeWorker(
            source_tag=tag,
            log_callback=self._cs_log,
            progress_callback=self._cs_progress_cb,
        )
        threading.Thread(target=self._cs_run, daemon=True).start()

    def _cs_run(self):
        self.cs_worker.run()
        enqueue(lambda: self.cs_btn_start.configure(state="normal"))
        enqueue(lambda: self.cs_btn_stop.configure(state="disabled"))
        enqueue(self._cs_refresh_count)
        enqueue(self._sc_refresh_count)
        enqueue(self._refresh_all_tag_selectors)

    def _cs_progress_cb(self, cur, total):
        enqueue(lambda: self.cs_lbl_count.configure(text=f"已处理约 {cur} 页..."))

    def _cs_stop(self):
        if self.cs_worker:
            self.cs_worker.stop()
        self._cs_log("停止信号已发送...")
        self.cs_btn_stop.configure(state="disabled")

    # ════════════════ TokenFinder 控制 ══════════════════════════════════
    def _tf_log(self, msg):
        def _do():
            self.tf_log.configure(state="normal")
            self.tf_log.insert("end", msg + "\n")
            self.tf_log.see("end")
            self.tf_log.configure(state="disabled")
        enqueue(_do)

    def _tf_refresh_count(self):
        self.tf_lbl_count.configure(text=f"数据库已有 x_links：{db.count_x_links()} 条")

    def _tf_start(self):
        tag = (self.tf_tag_entry.get() or "").strip()
        if not tag:
            self._tf_log("请填写 source tag（本批次分组标签，必填）")
            return
        if tag == "tg_left":
            self._tf_log("source tag 不能为保留值 'tg_left'")
            return
        self.tf_btn_start.configure(state="disabled")
        self.tf_btn_stop.configure(state="normal")
        self.tf_log.configure(state="normal")
        self.tf_log.delete("1.0", "end")
        self.tf_log.configure(state="disabled")
        self.tf_worker = TokenFinderWorker(
            source_tag=tag,
            log_callback=self._tf_log,
            progress_callback=self._tf_progress_cb,
        )
        threading.Thread(target=self._tf_run, daemon=True).start()

    def _tf_run(self):
        self.tf_worker.run()
        enqueue(lambda: self.tf_btn_start.configure(state="normal"))
        enqueue(lambda: self.tf_btn_stop.configure(state="disabled"))
        enqueue(self._tf_refresh_count)
        enqueue(self._refresh_all_tag_selectors)

    def _tf_progress_cb(self, cur, total):
        def _do():
            if total:
                self.tf_lbl_count.configure(text=f"进度 {cur}/{total}")
            else:
                self.tf_lbl_count.configure(text=f"已处理约 {cur} 条...")
        enqueue(_do)

    def _tf_stop(self):
        if self.tf_worker:
            self.tf_worker.stop()
        self._tf_log("停止信号已发送...")
        self.tf_btn_stop.configure(state="disabled")

    # ════════════════ 活动项目-Twitter 控制 ══════════════════════════════
    def _ct_log(self, msg):
        def _do():
            self.ct_log.configure(state="normal")
            self.ct_log.insert("end", msg + "\n")
            self.ct_log.see("end")
            self.ct_log.configure(state="disabled")
        enqueue(_do)

    def _ct_refresh_count(self):
        self.ct_lbl_count.configure(text=f"数据库已有 campaign：{db.count_x_links()} 条")

    def _ct_start(self):
        tag = (self.ct_tag_entry.get() or "").strip()
        if not tag:
            self._ct_log("请填写 source tag（本批次分组标签，必填）")
            return
        if tag == "tg_left":
            self._ct_log("source tag 不能为保留值 'tg_left'")
            return
        self.ct_btn_start.configure(state="disabled")
        self.ct_btn_stop.configure(state="normal")
        self.ct_log.configure(state="normal")
        self.ct_log.delete("1.0", "end")
        self.ct_log.configure(state="disabled")
        self.ct_worker = CampaignWorker(
            endpoint="/api/projects",
            field="twitter_handle",
            strip_at=True,
            source_tag=tag,
            log_callback=self._ct_log,
            progress_callback=self._ct_progress_cb,
        )
        threading.Thread(target=self._ct_run, daemon=True).start()

    def _ct_run(self):
        self.ct_worker.run()
        enqueue(lambda: self.ct_btn_start.configure(state="normal"))
        enqueue(lambda: self.ct_btn_stop.configure(state="disabled"))
        enqueue(self._ct_refresh_count)
        enqueue(self._refresh_all_tag_selectors)

    def _ct_progress_cb(self, cur, total):
        enqueue(lambda: self.ct_lbl_count.configure(text=f"已处理约 {cur} 页..."))

    def _ct_stop(self):
        if self.ct_worker:
            self.ct_worker.stop()
        self._ct_log("停止信号已发送...")
        self.ct_btn_stop.configure(state="disabled")

    # ════════════════ 活动项目-KOL 控制 ══════════════════════════════════
    def _ck_log(self, msg):
        def _do():
            self.ck_log.configure(state="normal")
            self.ck_log.insert("end", msg + "\n")
            self.ck_log.see("end")
            self.ck_log.configure(state="disabled")
        enqueue(_do)

    def _ck_refresh_count(self):
        self.ck_lbl_count.configure(text=f"数据库已有 campaign：{db.count_x_links()} 条")

    def _ck_start(self):
        tag = (self.ck_tag_entry.get() or "").strip()
        if not tag:
            self._ck_log("请填写 source tag（本批次分组标签，必填）")
            return
        if tag == "tg_left":
            self._ck_log("source tag 不能为保留值 'tg_left'")
            return
        self.ck_btn_start.configure(state="disabled")
        self.ck_btn_stop.configure(state="normal")
        self.ck_log.configure(state="normal")
        self.ck_log.delete("1.0", "end")
        self.ck_log.configure(state="disabled")
        self.ck_worker = CampaignWorker(
            endpoint="/api/kol-projects",
            field="project_handle",
            strip_at=False,
            source_tag=tag,
            log_callback=self._ck_log,
            progress_callback=self._ck_progress_cb,
        )
        threading.Thread(target=self._ck_run, daemon=True).start()

    def _ck_run(self):
        self.ck_worker.run()
        enqueue(lambda: self.ck_btn_start.configure(state="normal"))
        enqueue(lambda: self.ck_btn_stop.configure(state="disabled"))
        enqueue(self._ck_refresh_count)
        enqueue(self._refresh_all_tag_selectors)

    def _ck_progress_cb(self, cur, total):
        enqueue(lambda: self.ck_lbl_count.configure(text=f"已处理约 {cur} 页..."))

    def _ck_stop(self):
        if self.ck_worker:
            self.ck_worker.stop()
        self._ck_log("停止信号已发送...")
        self.ck_btn_stop.configure(state="disabled")

    # ════════════════ 官网爬虫控制（保留在 ScraperTab 主类）═════════════
    def _sc_log(self, msg):
        def _do():
            if hasattr(self, 'sc_log'):
                self.sc_log.configure(state="normal")
                self.sc_log.insert("end", msg + "\n")
                self.sc_log.see("end")
                self.sc_log.configure(state="disabled")
        enqueue(_do)

    def _sc_progress(self, cur, total):
        def _do():
            if hasattr(self, 'sc_progress'):
                self.sc_progress.set(cur / total if total else 0)
                self.sc_lbl_progress.configure(text=f"{cur} / {total}")
        enqueue(_do)

    def _sc_refresh_count(self):
        if hasattr(self, 'sc_lbl_count'):
            n = len(db.get_all_websites())
            self.sc_lbl_count.configure(text=f"待解析官网：{n} 个")

    def _sc_start(self):
        self._sc_refresh_count()
        self.sc_btn_start.configure(state="disabled")
        self.sc_btn_stop.configure(state="normal")
        self.sc_log.configure(state="normal")
        self.sc_log.delete("1.0", "end")
        self.sc_log.configure(state="disabled")
        self.sc_progress.set(0)
        self.sc_worker = ScraperWorker(
            self._sc_log, self._sc_progress,
            use_llm=self.var_use_llm.get() if hasattr(self, 'var_use_llm') else False
        )
        threading.Thread(target=self._sc_run, daemon=True).start()

    def _sc_run(self):
        self.sc_worker.run()
        enqueue(lambda: self.sc_btn_start.configure(state="normal"))
        enqueue(lambda: self.sc_btn_stop.configure(state="disabled"))
        enqueue(self._sc_refresh_count)
        enqueue(self._refresh_all_tag_selectors)

    def _sc_stop(self):
        if self.sc_worker:
            self.sc_worker.stop()
        self._sc_log("停止信号已发送...")
        self.sc_btn_stop.configure(state="disabled")

    # ════════════════ X 关键人搜索 ══════════════════════════════
    def _build_xps_panel(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(parent, text="X 关键人搜索",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(10, 4))
        ctk.CTkLabel(
            parent,
            text=(
                "对 x_links 中每个项目官号，在 X 搜索 People，\n"
                "找到将该 handle 写入个人 bio 的用户，\n"
                "筛选 CEO / CMO / Growth / Founder，写入 x_contacts 表。"
            ),
            text_color="gray", wraplength=420, justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 4))

        count_row = ctk.CTkFrame(parent, fg_color="transparent")
        count_row.pack(fill="x", padx=14, pady=(0, 2))
        self.xps_lbl_count = ctk.CTkLabel(count_row, text="", text_color="#4CAF50")
        self.xps_lbl_count.pack(side="left")
        ctk.CTkButton(count_row, text="重置已搜索", width=90, height=22,
                      fg_color="gray40", hover_color="gray30",
                      command=self._xps_reset).pack(side="left", padx=8)
        self._xps_refresh_count()

        self.xps_progress = ctk.CTkProgressBar(parent)
        self.xps_progress.pack(fill="x", padx=14, pady=6)
        self.xps_progress.set(0)
        self.xps_lbl_progress = ctk.CTkLabel(parent, text="", text_color="gray")
        self.xps_lbl_progress.pack()

        self.xps_log = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=11))
        self.xps_log.pack(fill="both", expand=True, padx=10, pady=4)
        self.xps_log.configure(state="disabled")

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=6)
        self.xps_btn_start = ctk.CTkButton(btn_row, text="▶ 开始搜索",
                                           command=self._xps_start)
        self.xps_btn_start.pack(side="left", padx=4)
        self.xps_btn_pause = ctk.CTkButton(
            btn_row, text="⏸ 暂停",
            fg_color="#e67e22", hover_color="#d35400",
            state="disabled", command=self._xps_pause)
        self.xps_btn_pause.pack(side="left", padx=4)
        self.xps_btn_resume = ctk.CTkButton(
            btn_row, text="▶ 恢复",
            fg_color="#27ae60", hover_color="#1e8449",
            state="disabled", command=self._xps_resume)
        self.xps_btn_resume.pack(side="left", padx=4)
        self.xps_btn_stop = ctk.CTkButton(
            btn_row, text="⏹ 停止",
            fg_color="#c0392b", hover_color="#922b21",
            state="disabled", command=self._xps_stop)
        self.xps_btn_stop.pack(side="left", padx=4)
        if sys.platform == 'darwin':
            self.xps_btn_ready = ctk.CTkButton(
                btn_row, text="已登录就绪",
                fg_color="#2196F3", hover_color="#1976D2",
                state="disabled", command=self._xps_ready)
            self.xps_btn_ready.pack(side="left", padx=4)

    def _xps_refresh_count(self):
        if hasattr(self, 'xps_lbl_count'):
            pending = len(db.get_x_links_for_profile_search())
            total   = db.count_x_contacts()
            self.xps_lbl_count.configure(
                text=f"待搜索：{pending} 个 | 已入库关键人：{total} 个"
            )

    def _xps_reset(self):
        db.reset_x_links_profile_search()
        self._xps_refresh_count()
        self._xps_log("已重置所有项目的搜索状态，下次运行将重新扫描所有 following 列表")

    def _xps_log(self, msg):
        def _do():
            self.xps_log.configure(state="normal")
            self.xps_log.insert("end", msg + "\n")
            self.xps_log.see("end")
            self.xps_log.configure(state="disabled")
        enqueue(_do)

    def _xps_progress(self, cur, total):
        def _do():
            val = cur / total if total else 0
            self.xps_progress.set(val)
            self.xps_lbl_progress.configure(text=f"{cur}/{total}")
        enqueue(_do)

    def _xps_start(self):
        self._xps_refresh_count()
        self.xps_btn_start.configure(state="disabled")
        self.xps_btn_pause.configure(state="normal")
        self.xps_btn_resume.configure(state="disabled")
        self.xps_btn_stop.configure(state="normal")
        if sys.platform == 'darwin' and hasattr(self, 'xps_btn_ready'):
            self.xps_btn_ready.configure(state="normal")
        self.xps_log.configure(state="normal")
        self.xps_log.delete("1.0", "end")
        self.xps_log.configure(state="disabled")
        self.xps_progress.set(0)
        self.xps_worker = XProfileSearchWorker(self._xps_log, self._xps_progress)
        threading.Thread(target=self._xps_run, daemon=True).start()

    def _xps_run(self):
        self.xps_worker.run()
        enqueue(lambda: self.xps_btn_start.configure(state="normal"))
        enqueue(lambda: self.xps_btn_pause.configure(state="disabled"))
        enqueue(lambda: self.xps_btn_resume.configure(state="disabled"))
        enqueue(lambda: self.xps_btn_stop.configure(state="disabled"))
        if sys.platform == 'darwin' and hasattr(self, 'xps_btn_ready'):
            enqueue(lambda: self.xps_btn_ready.configure(state="disabled"))
        enqueue(self._xps_refresh_count)

    def _xps_ready(self):
        if self.xps_worker and hasattr(self.xps_worker, 'set_ready'):
            self.xps_worker.set_ready()
            self.xps_btn_ready.configure(state="disabled")

    def _xps_pause(self):
        if self.xps_worker:
            self.xps_worker.pause()
        self.xps_btn_pause.configure(state="disabled")
        self.xps_btn_resume.configure(state="normal")

    def _xps_resume(self):
        if self.xps_worker:
            self.xps_worker.resume()
        self.xps_btn_pause.configure(state="normal")
        self.xps_btn_resume.configure(state="disabled")

    def _xps_stop(self):
        if self.xps_worker:
            self.xps_worker.resume()   # 解除暂停，让 _stop 能被检测到
            self.xps_worker.stop()
        self._xps_log("停止信号已发送...")
        self.xps_btn_pause.configure(state="disabled")
        self.xps_btn_resume.configure(state="disabled")
        self.xps_btn_stop.configure(state="disabled")
