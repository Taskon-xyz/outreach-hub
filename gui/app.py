"""
主窗口 App — 构建标签页（懒加载：仅在首次切换时初始化 Tab 内容）
"""
import customtkinter as ctk


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Web3 Outreach Hub")
        self.geometry("900x640")
        self.resizable(True, True)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._build_ui()

    def _build_ui(self):
        # Tabview 自然填满窗口，移除固定尺寸锁
        # 拖动/最大化时内容自动随窗口缩放
        self.tabs = ctk.CTkTabview(self, command=self._on_tab_changed)
        self.tabs.pack(padx=10, pady=10, fill="both", expand=True)

        # Tab 名称 → (模块路径, 类名) 的映射，用于延迟 import
        self._tab_registry = {
            "📊 仪表盘": ("gui.tab_dashboard", "DashboardTab"),
            "🔍 爬虫":   ("gui.tab_scraper",   "ScraperTab"),
            "🔬 解析":   ("gui.tab_parser",    "ParserTab"),
            "✉️ 文案":   ("gui.tab_messages",  "MessagesTab"),
            "📤 发送":   ("gui.tab_sender",    "SenderTab"),
            "📋 记录":   ("gui.tab_history",   "HistoryTab"),
            "⚙️ 设置":   ("gui.tab_settings",  "SettingsTab"),
        }
        self._loaded_tabs = {}  # 已初始化的 Tab 实例

        for name in self._tab_registry:
            self.tabs.add(name)

        # 仅首屏（仪表盘）立即加载
        self._ensure_tab("📊 仪表盘")

    def _on_tab_changed(self):
        """CTkTabview 切换回调"""
        name = self.tabs.get()
        self._ensure_tab(name)

    def _ensure_tab(self, name):
        """首次访问时才 import 并实例化对应 Tab 类"""
        if name in self._loaded_tabs:
            return
        entry = self._tab_registry.get(name)
        if not entry:
            return
        module_path, class_name = entry
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        self._loaded_tabs[name] = cls(self.tabs.tab(name))
