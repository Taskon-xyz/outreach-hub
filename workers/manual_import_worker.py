"""
手动导入 Worker — 从 Excel/CSV 文件批量导入项目数据
支持列名：项目名/官网/X handle/TG handle/邮箱
"""
import re

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
from workers.base_worker import BaseWorker


# 列名映射：标准列名 → 可接受的别名列表（小写）
COLUMN_ALIASES = {
    "company_name": ["company_name", "项目名", "name", "project_name", "公司名", "项目名称"],
    "website":      ["website", "官网", "url", "site", "网站"],
    "x_handle":     ["x_handle", "x", "twitter", "x账号", "x账号链接", "twitter_handle"],
    "tg_handle":    ["tg_handle", "telegram", "tg", "tg账号", "telegram_handle"],
    "email":        ["email", "邮箱", "e-mail", "邮件"],
}


def _split_multi(val):
    """将逗号/分号/中文逗号分隔的多个值拆分为列表"""
    if not val:
        return []
    return [v.strip() for v in re.split(r'[,;，；]', str(val)) if v.strip()]


class ManualImportWorker(BaseWorker):
    def __init__(self, file_path, source_tag, log_callback, progress_callback=None):
        super().__init__(log_callback, progress_callback)
        if not source_tag or source_tag == "tg_left":
            raise ValueError("source_tag 必填，且不能为保留值 'tg_left'")
        self.file_path = file_path
        self.source_tag = source_tag

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.safe_log(f"[错误] {e}")

    def _run(self):
        import pandas as pd

        ext = os.path.splitext(self.file_path)[1].lower()
        self.safe_log(f"读取文件：{os.path.basename(self.file_path)}")

        try:
            if ext in (".xlsx", ".xls"):
                df = pd.read_excel(self.file_path, engine="openpyxl")
            elif ext == ".csv":
                df = pd.read_csv(self.file_path)
            else:
                self.safe_log(f"不支持的文件格式：{ext}，请使用 .xlsx / .xls / .csv")
                return
        except Exception as e:
            self.safe_log(f"读取文件失败：{e}")
            return

        if df.empty:
            self.safe_log("文件为空，无数据可导入。")
            return

        # 匹配列名
        col_map = self._match_columns(df.columns.tolist())
        self.safe_log(f"识别到列：{', '.join(f'{k}←{v}' for k, v in col_map.items())}")

        total = len(df)
        self.safe_log(f"共 {total} 行数据")

        stats = {"projects": 0, "x_links": 0, "tg_links": 0, "emails": 0, "errors": 0}

        for idx, row in df.iterrows():
            if self._stop:
                self.safe_log("已停止。")
                break

            try:
                self._process_row(row, col_map, stats)
            except Exception as e:
                stats["errors"] += 1
                self.safe_log(f"  第 {idx + 1} 行错误：{e}")

            if (idx + 1) % 10 == 0 or idx + 1 == total:
                self.progress(idx + 1, total)

        self.safe_log(
            f"\n导入完成：项目 {stats['projects']}，"
            f"X handles {stats['x_links']}，"
            f"TG {stats['tg_links']}，"
            f"邮箱 {stats['emails']}"
        )
        if stats["errors"]:
            self.safe_log(f"错误 {stats['errors']} 行")

    def _match_columns(self, columns):
        """将 DataFrame 列名映射到标准字段名"""
        col_map = {}
        normalized = {c.strip().lower(): c for c in columns}

        for std_name, aliases in COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in normalized:
                    col_map[std_name] = normalized[alias]
                    break

        return col_map

    def _get_val(self, row, col_map, key):
        """从行中获取指定字段的值，不存在则返回空字符串"""
        col = col_map.get(key)
        if not col:
            return ""
        val = row.get(col)
        if val is None or (isinstance(val, float) and val != val):  # NaN check
            return ""
        return str(val).strip()

    def _process_row(self, row, col_map, stats):
        company_name = self._get_val(row, col_map, "company_name")
        website = self._get_val(row, col_map, "website")
        x_raw = self._get_val(row, col_map, "x_handle")
        tg_raw = self._get_val(row, col_map, "tg_handle")
        email_raw = self._get_val(row, col_map, "email")

        # 创建项目（有 website 时才建）
        project_id = None
        if website and website.lower() not in ("none", "null", "nan", ""):
            if not website.startswith("http"):
                website = "https://" + website
            pid, is_new = db.upsert_project_return_id(
                company_name, website, source=self.source_tag
            )
            if pid:
                project_id = pid
                if is_new:
                    stats["projects"] += 1
                    # 标记为已爬取（手动导入不需要再爬）
                    db.mark_project_scraped(project_id)

        # X handles
        for h in _split_multi(x_raw):
            if h.lower() in ("none", "null", "nan", ""):
                continue
            if db.insert_x_link(project_id, h, source=self.source_tag):
                stats["x_links"] += 1

        # TG handles / links
        for h in _split_multi(tg_raw):
            if h.lower() in ("none", "null", "nan", ""):
                continue
            if "t.me" in h or "telegram.me" in h:
                # TG 群链接 → tg_links
                if db.insert_tg_link(project_id, h, source=self.source_tag):
                    stats["tg_links"] += 1
            else:
                # TG username → 直接写入 tg_contacts
                username = h.lstrip("@").lower()
                if username:
                    db.insert_tg_handle(
                        username, role=None, group_name=None,
                        source_link=None, project_id=project_id,
                        source=self.source_tag,
                    )
                    stats["tg_links"] += 1

        # Emails
        for h in _split_multi(email_raw):
            if h.lower() in ("none", "null", "nan", ""):
                continue
            if db.insert_email(project_id, h, source=self.source_tag):
                stats["emails"] += 1
