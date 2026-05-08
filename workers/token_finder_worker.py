"""
Token Finder Worker — 从 token-finder.taskon.xyz 抓取 Twitter 账号
仅提取 twitter_handle，写入 x_links 表（无 project_id）
纯 API 翻页，offset += limit 直到拿完
"""
import re

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workers.base_worker import BaseWorker


class TokenFinderWorker(BaseWorker):
    BASE_URL = (
        "https://token-finder.taskon.xyz/api/projects"
        "?search=&priority=&min_score=0&limit=50&offset={offset}"
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

        offset     = 0
        limit      = 50
        total      = None
        total_new  = 0
        total_skip = 0

        while not self._stop:
            url = self.BASE_URL.format(offset=offset)
            self.log(f"请求 offset={offset} ...")
            resp = requests.get(url, timeout=20)
            if resp.status_code != 200:
                self.log(f"请求失败 [{resp.status_code}]，停止。")
                break

            data = resp.json()
            projects = data.get("projects", []) or []

            if total is None:
                total = data.get("total", 0)
                self.log(f"共 {total} 条，每页 {limit}，约 {(total + limit - 1) // limit} 页")

            if not projects:
                self.log("本页无数据，停止。")
                break

            new_n, skip_n = self._process(projects)
            total_new  += new_n
            total_skip += skip_n
            self.log(f"  新增 {new_n}，已存在 {skip_n}")
            self.progress(offset + len(projects), total)

            if offset + limit >= total:
                self.log("已到最后一页，停止。")
                break

            offset += limit

        self.log(f"\n完成，新增 {total_new} 条 x_links")

    def _process(self, projects):
        import db
        imported = 0
        skipped  = 0
        for p in projects:
            handle = str(p.get("twitter_handle") or "").strip()
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
        if handle.startswith("http"):
            m = re.search(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,15})", handle)
            return f"https://x.com/{m.group(1)}" if m else None
        if handle.startswith("@"):
            return f"https://x.com/{handle[1:]}"
        return f"https://x.com/{handle}"
