"""
ChainScope Worker — 从 chainscope.taskon.xyz 抓取项目官网和 Twitter
字段：project_name / website / twitter
纯 API 翻页，数据与上一页完全一致则停止
"""
import re

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
from workers.base_worker import BaseWorker


class ChainScopeWorker(BaseWorker):
    BASE_URL = (
        "https://chainscope.taskon.xyz/api/leads"
        "?tier=all&date=&status=all&search=&sort=lead_date&order=desc"
        "&page={page}&page_size=50"
    )

    def __init__(self, source_tag, log_callback, progress_callback=None):
        super().__init__(log_callback, progress_callback)
        if not source_tag or source_tag == "tg_left":
            raise ValueError("source_tag 必填，且不能为保留值 'tg_left'")
        self.source_tag = source_tag

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.log(f"[错误] {e}")

    def _run(self):
        import requests

        page_num   = 1
        prev_items = None
        total_new  = 0
        total_skip = 0

        while not self._stop:
            url = self.BASE_URL.format(page=page_num)
            self.log(f"请求第 {page_num} 页...")
            resp = requests.get(url, timeout=20)
            if resp.status_code != 200:
                self.log(f"请求失败 [{resp.status_code}]，停止。")
                break

            data = resp.json()
            items = data.get("items", []) or []
            total = data.get("total", 0)
            page_size = data.get("page_size", 50)

            if page_num == 1:
                self.log(f"共 {total} 条，每页 {page_size}，约 {(total + page_size - 1) // page_size} 页")

            # 数据与上一页完全一致 → 已到尽头
            if items == prev_items:
                self.log("数据与上页一致，已到最后一页，停止。")
                break

            if not items:
                self.log("本页无数据，停止。")
                break

            prev_items = items
            new_n, skip_n = self._process_page(items)
            total_new  += new_n
            total_skip += skip_n
            self.log(f"  新增 {new_n}，已存在 {skip_n}")
            self.progress(page_num, None)

            page_num += 1

        self.log(f"\n完成，共 {page_num - 1} 页，新增 {total_new} 条")

    def _process_page(self, items):
        imported = 0
        skipped  = 0
        for row in items:
            project_name = str(row.get("project_name") or "").strip()
            website      = str(row.get("website")       or "").strip()
            twitter      = str(row.get("twitter")       or "").strip()

            if not website or website.lower() in ("none", "null", ""):
                skipped += 1
                continue

            if not website.startswith("http"):
                website = "https://" + website

            project_id, is_new = db.upsert_project_return_id(project_name, website, source=self.source_tag)
            if not project_id:
                skipped += 1
                continue

            if is_new:
                imported += 1
            else:
                skipped += 1

            if twitter and twitter.lower() not in ("none", "null", ""):
                normalized = self._normalize_twitter(twitter)
                if normalized:
                    db.insert_x_link(project_id, normalized, source=self.source_tag)

        return imported, skipped

    def _normalize_twitter(self, handle):
        handle = handle.strip()
        if not handle:
            return None
        if handle.startswith("http"):
            m = re.search(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,15})", handle)
            if m:
                return f"https://x.com/{m.group(1)}"
            return None
        if handle.startswith("@"):
            return f"https://x.com/{handle[1:]}"
        return f"https://x.com/{handle}"
