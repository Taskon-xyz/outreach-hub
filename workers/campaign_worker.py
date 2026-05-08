"""
Campaign Worker — 从 xkeyword-monitor.taskon.xyz 抓取 Twitter 账号
两个数据源：
  1. /api/projects        → 字段 Twitter_handle（有 @ 前缀，需去掉）
  2. /api/kol-projects    → 字段 project_handle（无 @ 前缀）
source 统一标记为 'campaign'
page-based 翻页，page += 1 直到拿完全部
"""
import re

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.base_worker import BaseWorker


class CampaignWorker(BaseWorker):
    """
    endpoint : API 路径，如 '/api/projects'
    field    : 推特 handle 在 JSON 中的字段名
    strip_at : 是否去掉开头的 @ 符号
    """
    BASE_URL = "https://xkeyword-monitor.taskon.xyz{endpoint}?page={page}&page_size=50"

    def __init__(self, endpoint, field, strip_at, source_tag, log_callback, progress_callback=None):
        super().__init__(log_callback, progress_callback)
        if not source_tag or source_tag == "tg_left":
            raise ValueError("source_tag 必填，且不能为保留值 'tg_left'")
        self.endpoint   = endpoint
        self.field      = field
        self.strip_at   = strip_at
        self.source_tag = source_tag

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.log(f"[错误] {e}")

    def _run(self):
        import requests

        page_num   = 1
        page_size  = 50
        total_new  = 0
        total_skip = 0

        while not self._stop:
            url = self.BASE_URL.format(endpoint=self.endpoint, page=page_num)
            self.log(f"请求第 {page_num} 页...")
            try:
                resp = requests.get(url, timeout=20)
            except Exception as e:
                self.log(f"请求失败：{e}，停止。")
                break

            if resp.status_code != 200:
                self.log(f"请求失败 [{resp.status_code}]，停止。")
                break

            data = resp.json()
            # 统一兼容两种返回格式
            items    = data.get("items", []) or data.get("data", []) or []
            total    = data.get("total", 0)
            returned = len(items)

            if page_num == 1 and total:
                self.log(f"共 {total} 条，每页 {page_size}，约 {(total + page_size - 1) // page_size} 页")

            if returned == 0:
                self.log("本页无数据，停止。")
                break

            new_n, skip_n = self._process(items)
            total_new  += new_n
            total_skip += skip_n
            self.log(f"  新增 {new_n}，已存在/无效 {skip_n}")
            self.progress(page_num, None)

            # page_size 以下视为最后一页
            if returned < page_size:
                self.log("数据少于一页，已到最后一页，停止。")
                break

            page_num += 1

        self.log(f"\n完成，共 {page_num - 1} 页，新增 {total_new} 条 campaign")

    def _process(self, items):
        import db
        imported = 0
        skipped  = 0
        for row in items:
            handle = str(row.get(self.field) or "").strip()
            if not handle or handle.lower() in ("none", "null", ""):
                skipped += 1
                continue
            normalized = self._normalize(handle)
            if not normalized:
                skipped += 1
                continue
            if db.insert_x_link(None, normalized, source=self.source_tag):
                imported += 1
            else:
                skipped += 1
        return imported, skipped

    def _normalize(self, handle):
        handle = handle.strip()
        if not handle:
            return None
        # 去掉开头的 @
        if handle.startswith("@"):
            handle = handle[1:]
        # 处理完整 URL
        if handle.startswith("http"):
            m = re.search(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,15})", handle)
            return f"https://x.com/{m.group(1)}" if m else None
        # 纯 handle
        return f"https://x.com/{handle}"
