"""
SQLite 数据库 — 所有读写操作
"""
import sqlite3
import os
from datetime import datetime
from config import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "outreach.db")

# ── API 客户端模式（局域网其他电脑发送时启用）──────────────────────────────
# config.API_BASE 留空 = 本机 SQLite 模式；填写 http://192.168.x.x:5000 = 客户端模式
import config as _config

def _api_url(path):
    base = getattr(_config, "API_BASE", "")
    return f"{base}/api/{path}" if base else ""


def _api_get(path):
    url = _api_url(path)
    if not url:
        return None
    import requests
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0:
        raise Exception(data.get("msg", "api error"))
    return data.get("data")


def _api_post(path, payload):
    url = _api_url(path)
    if not url:
        return None
    import requests
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0:
        raise Exception(data.get("msg", "api error"))
    return data.get("data")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """建表（幂等）"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS projects (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name  TEXT,
        website       TEXT UNIQUE,
        crunchbase_url TEXT,
        imported_at   DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS tg_links (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id   INTEGER REFERENCES projects(id),
        link         TEXT UNIQUE,
        parse_status TEXT,
        parse_error  TEXT,
        extracted_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS x_links (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id  INTEGER REFERENCES projects(id),
        handle      TEXT UNIQUE,
        extracted_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS tg_handles (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id  INTEGER REFERENCES projects(id),
        username    TEXT UNIQUE,
        role        TEXT,
        group_name  TEXT,
        source_link TEXT,
        parsed_at   DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS tg_left_users (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        username     TEXT UNIQUE,
        display_name TEXT,
        bio          TEXT,
        group_name   TEXT,
        found_at     DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- 合并表：tg_handles + tg_left_users 的统一候选池
    -- source: 'parsed'（原 tg_handles，含 imported 和群解析）| 'tg_left'（原 tg_left_users，最高优先级）
    -- role: 'Owner'/'Admin' 仅 parsed 侧有值；tg_left 为 NULL
    CREATE TABLE IF NOT EXISTS tg_contacts (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id   INTEGER REFERENCES projects(id),
        username     TEXT UNIQUE,
        role         TEXT,
        group_name   TEXT,
        source       TEXT,
        source_link  TEXT,
        display_name TEXT,
        bio          TEXT,
        skip_reason  TEXT,
        skipped_at   DATETIME,
        added_at     DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS send_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        handle       TEXT,
        channel      TEXT,
        source       TEXT,
        message_name TEXT,
        sent_at      DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS message_templates (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        channel    TEXT,
        name       TEXT,
        content    TEXT,
        is_active  INTEGER DEFAULT 0,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS emails (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id  INTEGER REFERENCES projects(id),
        email       TEXT UNIQUE,
        source      TEXT,
        extracted_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    );
    """)
    conn.commit()
    # 为旧数据库补加列（幂等，列已存在时忽略）
    for sql in [
        "ALTER TABLE tg_links ADD COLUMN parse_status TEXT",
        "ALTER TABLE tg_links ADD COLUMN parse_error  TEXT",
        "ALTER TABLE projects ADD COLUMN scrape_status TEXT",
        "ALTER TABLE tg_handles ADD COLUMN skip_reason TEXT",
        "ALTER TABLE tg_handles ADD COLUMN skipped_at DATETIME",
        "ALTER TABLE tg_left_users ADD COLUMN skip_reason TEXT",
        "ALTER TABLE tg_left_users ADD COLUMN skipped_at DATETIME",
        "ALTER TABLE x_links ADD COLUMN source TEXT",
        "ALTER TABLE projects ADD COLUMN source TEXT",
        "ALTER TABLE tg_left_users ADD COLUMN project_id INTEGER REFERENCES projects(id)",
        "ALTER TABLE tg_links ADD COLUMN source TEXT",
    ]:
        try:
            conn.execute(sql)
            conn.commit()
        except Exception:
            pass
    # 一次性数据迁移：tg_handles + tg_left_users → tg_contacts
    _migrate_tg_contacts(conn)
    conn.close()


def _migrate_tg_contacts(conn):
    """把 tg_handles + tg_left_users 的数据迁移到 tg_contacts（幂等，靠 settings 标记）。

    规则：
    - tg_left_users 先迁，source='tg_left'
    - tg_handles 后迁，source='parsed'；同 username 冲突时 tg_left 不被覆盖（INSERT OR IGNORE）
    - 旧表保留不删，可回滚
    """
    marker = conn.execute(
        "SELECT value FROM settings WHERE key='tg_contacts_migrated'"
    ).fetchone()
    if marker and marker["value"] == "1":
        return

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    if "tg_left_users" in tables:
        conn.execute("""
            INSERT OR IGNORE INTO tg_contacts
                (project_id, username, role, group_name, source,
                 display_name, bio, skip_reason, skipped_at, added_at)
            SELECT project_id, username, NULL, group_name, 'tg_left',
                   display_name, bio, skip_reason, skipped_at, found_at
            FROM tg_left_users
            WHERE username IS NOT NULL AND username != ''
        """)

    if "tg_handles" in tables:
        # source 通过 LEFT JOIN projects 继承；project_id 为空或 projects.source 为空时
        # → tg_contacts.source = NULL（只在发送页 all 下可见）
        conn.execute("""
            INSERT OR IGNORE INTO tg_contacts
                (project_id, username, role, group_name, source, source_link,
                 skip_reason, skipped_at, added_at)
            SELECT h.project_id, h.username, h.role, h.group_name,
                   p.source, h.source_link,
                   h.skip_reason, h.skipped_at, h.parsed_at
            FROM tg_handles h
            LEFT JOIN projects p ON h.project_id = p.id
            WHERE h.username IS NOT NULL AND h.username != ''
        """)

    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('tg_contacts_migrated', '1')"
    )
    conn.commit()


# ─── Projects ────────────────────────────────────────────────
def upsert_project(company_name, website, crunchbase_url="", source=None):
    website = _normalize_website(website)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO projects (company_name, website, crunchbase_url, source) VALUES (?,?,?,?)",
            (company_name, website, crunchbase_url, source)
        )
        # 如果已存在且有更高优先级的 source，补充标记
        if source:
            conn.execute(
                "UPDATE projects SET source=? WHERE website=? AND source IS NULL",
                (source, website)
            )
        conn.commit()
        row = conn.execute("SELECT id FROM projects WHERE website=?", (website,)).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def upsert_project_return_id(company_name, website, source=None):
    """
    写入 projects 表（website UNIQUE）。
    返回 (project_id, is_new) 元组；is_new=True 表示新增，False 表示已存在。
    """
    website = _normalize_website(website)
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO projects (company_name, website, source) VALUES (?,?,?)",
            (company_name, website, source)
        )
        is_new = cur.rowcount > 0
        if source:
            conn.execute(
                "UPDATE projects SET source=? WHERE website=? AND source IS NULL",
                (source, website)
            )
        conn.commit()
        row = conn.execute("SELECT id FROM projects WHERE website=?", (website,)).fetchone()
        return (row["id"], is_new) if row else (None, False)
    finally:
        conn.close()


def count_projects():
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    finally:
        conn.close()


def get_all_source_tags():
    """返回所有表中非空的 source 值（去重排序），排除内部保留值"""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT DISTINCT source FROM (
                SELECT source FROM projects WHERE source IS NOT NULL AND source != ''
                UNION
                SELECT source FROM x_links WHERE source IS NOT NULL AND source != ''
                UNION
                SELECT source FROM tg_links WHERE source IS NOT NULL AND source != ''
                UNION
                SELECT source FROM emails WHERE source IS NOT NULL AND source != ''
            ) WHERE source NOT IN ('parsed', 'tg_left')
            ORDER BY source
        """).fetchall()
        return [r["source"] for r in rows]
    finally:
        conn.close()


def get_all_websites():
    """返回未扫描过的官网（scrape_status IS NULL），包含 source 标记"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, website, source FROM projects"
            " WHERE website IS NOT NULL AND website != ''"
            "   AND (scrape_status IS NULL OR scrape_status != 'done')"
        ).fetchall()
        return [(r["id"], r["website"], r["source"]) for r in rows]
    finally:
        conn.close()


def mark_project_scraped(project_id):
    conn = get_conn()
    try:
        conn.execute("UPDATE projects SET scrape_status='done' WHERE id=?", (project_id,))
        conn.commit()
    finally:
        conn.close()


# ─── Emails ──────────────────────────────────────────────────
def insert_email(project_id, email, source=None):
    """写入 emails 表。返回 True=新增，False=已存在。"""
    email = email.strip().lower()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO emails (project_id, email, source) VALUES (?,?,?)",
            (project_id, email, source)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def count_emails():
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    finally:
        conn.close()


def get_unsent_emails(source=None):
    """返回未发送过邮件的邮箱列表（遵守冷却期）"""
    clause, params = _cooldown_clause("email", col="email")
    conn = get_conn()
    try:
        if source:
            rows = conn.execute(
                f"SELECT email FROM emails WHERE source=? AND {clause}",
                (source,) + params
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT email FROM emails WHERE {clause}",
                params
            ).fetchall()
        return [r["email"] for r in rows]
    finally:
        conn.close()


# ─── TG Links ────────────────────────────────────────────────
def insert_tg_link(project_id, link, source=None):
    """写入 tg_links 表。返回 True=新增，False=已存在（去重）。

    source: 自定义 tag。未提供时从 projects.source 继承。
            禁止使用保留值 'tg_left'。
    """
    if source == 'tg_left':
        raise ValueError("source='tg_left' 是保留值，不可用于 tg_links")
    conn = get_conn()
    try:
        if source is None and project_id is not None:
            row = conn.execute(
                "SELECT source FROM projects WHERE id=?", (project_id,)
            ).fetchone()
            if row and row["source"]:
                source = row["source"]
        cur = conn.execute(
            "INSERT OR IGNORE INTO tg_links (project_id, link, source) VALUES (?,?,?)",
            (project_id, link, source)
        )
        # 存量 source 为 NULL 时，本次传入补齐
        if source:
            conn.execute(
                "UPDATE tg_links SET source=? WHERE link=? AND source IS NULL",
                (source, link)
            )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def count_tg_links():
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM tg_links").fetchone()[0]
    finally:
        conn.close()


def get_all_tg_links():
    """返回所有未成功解析的 TG 群链接（parse_status != 'ok'），包含 project_id 和 source"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, link, project_id, source FROM tg_links"
            " WHERE parse_status IS NULL OR parse_status != 'ok'"
        ).fetchall()
        return [(r["id"], r["link"], r["project_id"], r["source"]) for r in rows]
    finally:
        conn.close()


def update_tg_link_status(link_id, status, error=None):
    """更新 TG 群链接解析状态：status='ok' 或 'failed'"""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE tg_links SET parse_status=?, parse_error=? WHERE id=?",
            (status, error, link_id)
        )
        conn.commit()
    finally:
        conn.close()


# ─── X Links ─────────────────────────────────────────────────
def _normalize_x_handle(handle):
    """统一转为 https://x.com/username 格式（小写），支持完整URL/@ handle/纯用户名"""
    import re
    handle = handle.strip()
    if handle.startswith('http'):
        m = re.search(r'(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,15})', handle)
        if m:
            return f"https://x.com/{m.group(1).lower()}"
        return handle.lower()
    if handle.startswith('@'):
        return f"https://x.com/{handle[1:].lower()}"
    return f"https://x.com/{handle.lower()}"


def _normalize_website(url):
    """统一官网 URL：小写、去尾斜杠、去 www."""
    if not url:
        return url
    url = url.strip().lower().rstrip('/')
    # http://www.example.com -> http://example.com
    url = url.replace('://www.', '://')
    return url


def insert_x_link(project_id, handle, source=None):
    """
    写入 x_links 表。返回 True=新增或补充标签，False=已存在（去重）。

    source: 'cb_excel' | 'cb_discover' | 'rootdata' | 'chainscope'
            | 'tokenfinder' | 'campaign' | None（存量数据）

    行为：
    - handle 不存在 → INSERT，返回 True
    - handle 已存在，source 为 NULL → UPDATE source（补充标签），返回 True
    - handle 已存在，source 已有值 → 跳过（不覆盖已有标签），返回 False
    """
    if source is None:
        conn = get_conn()
        try:
            normalized = _normalize_x_handle(handle)
            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO x_links (project_id, handle, source) VALUES (?,?,?)",
                    (project_id, normalized, source)
                )
            except Exception:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO x_links (project_id, handle) VALUES (?,?)",
                    (project_id, normalized)
                )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # 有 source 标签：先尝试 UPDATE 存量 NULL 记录
    conn = get_conn()
    try:
        normalized = _normalize_x_handle(handle)
        n = conn.execute(
            "UPDATE x_links SET source=? WHERE handle=? AND source IS NULL",
            (source, normalized)
        ).rowcount
        conn.commit()
        if n > 0:
            return True  # 补充标签
        # 尝试 INSERT（不存在 → 成功；已存在非 NULL source → rowcount=0）
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO x_links (project_id, handle, source) VALUES (?,?,?)",
                (project_id, normalized, source)
            )
        except Exception:
            cur = conn.execute(
                "INSERT OR IGNORE INTO x_links (project_id, handle) VALUES (?,?)",
                (project_id, normalized)
            )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def count_x_links():
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM x_links").fetchone()[0]
    finally:
        conn.close()


def get_unsent_x_handles(source=None):
    """
    返回可发送的 twitter handle（冷却期内发过的除外）。
    source: None=全部 | 'cb_excel' | 'cb_discover' | 'rootdata'
            | 'chainscope' | 'tokenfinder' | 'campaign'
    """
    result = _api_get(f"queue/x?source={source}" if source else "queue/x")
    if result is not None:
        return result
    clause, params = _cooldown_clause("twitter", col="handle")
    conn = get_conn()
    try:
        if source:
            rows = conn.execute(
                f"SELECT handle FROM x_links WHERE source=? AND {clause}",
                (source,) + params
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT handle FROM x_links WHERE {clause}",
                params
            ).fetchall()
        return [r["handle"] for r in rows]
    finally:
        conn.close()


# ─── TG Contacts（合并后的统一表；原 tg_handles + tg_left_users）───────
# source 枚举：
#   'parsed'  = 原 tg_handles（含 imported 和群解析管理员）
#   'tg_left' = 原 tg_left_users（最高优先级，不可被 parsed 覆盖）
def insert_tg_handle(username, role, group_name, source_link, project_id=None, source=None):
    """写入 tg_contacts。source 为自定义 tag；未提供时从 projects.source 继承。
    'tg_left' 是保留值，禁止通过本函数写入。已是 tg_left 的 username 不被覆盖。
    """
    if not username:
        return
    if source == 'tg_left':
        raise ValueError("source='tg_left' 是保留值，只能通过 insert_tg_left_user 写入")
    username = username.lower().strip().lstrip('@')
    suffix = get_setting("tg_import_filter_suffix", "bot")
    if suffix and username.endswith(suffix.lower()):
        return
    conn = get_conn()
    try:
        # 未提供 source 时，尝试从 projects 继承
        if source is None and project_id is not None:
            row = conn.execute(
                "SELECT source FROM projects WHERE id=?", (project_id,)
            ).fetchone()
            if row and row["source"]:
                source = row["source"]
        conn.execute(
            """INSERT INTO tg_contacts
                  (project_id, username, role, group_name, source, source_link)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(username) DO UPDATE SET
                   project_id  = COALESCE(excluded.project_id, tg_contacts.project_id),
                   role        = excluded.role,
                   group_name  = excluded.group_name,
                   source      = COALESCE(excluded.source, tg_contacts.source),
                   source_link = excluded.source_link
               WHERE tg_contacts.source IS NULL OR tg_contacts.source != 'tg_left'""",
            (project_id, username, role, group_name, source, source_link)
        )
        conn.commit()
    finally:
        conn.close()


def count_tg_handles():
    """统计所有非 tg_left 的 tg_contacts 记录数（原 tg_handles 表对应语义）"""
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM tg_contacts"
            " WHERE source IS NULL OR source != 'tg_left'"
        ).fetchone()[0]
    finally:
        conn.close()


def get_unsent_tg_admin_handles():
    """非 tg_left 的全部 tg_contacts，冷却期内已发和已跳过的除外"""
    result = _api_get("queue/tg_admin")
    if result is not None:
        return result
    clause, params = _cooldown_clause("telegram", col="username")
    conn = get_conn()
    try:
        rows = conn.execute(
            f"SELECT username FROM tg_contacts"
            f" WHERE (source IS NULL OR source != 'tg_left')"
            f"   AND skip_reason IS NULL AND {clause}",
            params
        ).fetchall()
        return [r["username"] for r in rows]
    finally:
        conn.close()


def get_unsent_tg_imported_handles():
    """仓库导入的记录（source_link='google_sheet_import' 且非 tg_left）"""
    result = _api_get("queue/tg_imported")
    if result is not None:
        return result
    clause, params = _cooldown_clause("telegram", col="username")
    conn = get_conn()
    try:
        rows = conn.execute(
            f"SELECT username FROM tg_contacts"
            f" WHERE source_link = 'google_sheet_import'"
            f"   AND (source IS NULL OR source != 'tg_left')"
            f"   AND skip_reason IS NULL"
            f"   AND {clause}",
            params
        ).fetchall()
        return [r["username"] for r in rows]
    finally:
        conn.close()


def get_unsent_tg_parsed_handles():
    """群解析出来的记录（source_link != 'google_sheet_import' 且非 tg_left）"""
    result = _api_get("queue/tg_parsed")
    if result is not None:
        return result
    clause, params = _cooldown_clause("telegram", col="username")
    conn = get_conn()
    try:
        rows = conn.execute(
            f"SELECT username FROM tg_contacts"
            f" WHERE (source_link IS NULL OR source_link != 'google_sheet_import')"
            f"   AND (source IS NULL OR source != 'tg_left')"
            f"   AND skip_reason IS NULL"
            f"   AND {clause}",
            params
        ).fetchall()
        return [r["username"] for r in rows]
    finally:
        conn.close()


# ─── TG Left Users（映射到 tg_contacts where source='tg_left'）──────
def insert_tg_left_user(username, display_name, bio, group_name, project_id=None):
    """写入 tg_contacts，source='tg_left'。优先级最高：已有记录也强制提升为 tg_left。"""
    if not username:
        return
    username = username.lower().strip().lstrip('@')
    suffix = get_setting("tg_import_filter_suffix", "bot")
    if suffix and username.endswith(suffix.lower()):
        return
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO tg_contacts
                  (project_id, username, group_name, source, display_name, bio)
               VALUES (?,?,?,'tg_left',?,?)
               ON CONFLICT(username) DO UPDATE SET
                   source       = 'tg_left',
                   display_name = COALESCE(excluded.display_name, tg_contacts.display_name),
                   bio          = COALESCE(excluded.bio,          tg_contacts.bio),
                   group_name   = COALESCE(excluded.group_name,   tg_contacts.group_name),
                   project_id   = COALESCE(tg_contacts.project_id, excluded.project_id)""",
            (project_id, username, group_name, display_name, bio)
        )
        conn.commit()
    finally:
        conn.close()


def count_tg_left_users():
    """统计 source='tg_left' 的记录数"""
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM tg_contacts WHERE source='tg_left'"
        ).fetchone()[0]
    finally:
        conn.close()


def get_unsent_tg_left_handles():
    """source='tg_left'，冷却期内已发和已跳过的除外"""
    result = _api_get("queue/tg_left")
    if result is not None:
        return result
    clause, params = _cooldown_clause("telegram", col="username")
    conn = get_conn()
    try:
        rows = conn.execute(
            f"SELECT username FROM tg_contacts"
            f" WHERE source='tg_left' AND skip_reason IS NULL AND {clause}",
            params
        ).fetchall()
        return [r["username"] for r in rows]
    finally:
        conn.close()


def get_unsent_tg_by_source(source=None):
    """按 source 筛选的统一接口。
    source: None | 'all' → 全部（含 NULL 记录）
            具体 tag（含 'tg_left'）→ WHERE source=? （NULL 自动排除）
    """
    clause, params = _cooldown_clause("telegram", col="username")
    conn = get_conn()
    try:
        if source in (None, "all"):
            rows = conn.execute(
                f"SELECT username FROM tg_contacts"
                f" WHERE skip_reason IS NULL AND {clause}",
                params
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT username FROM tg_contacts"
                f" WHERE source=? AND skip_reason IS NULL AND {clause}",
                (source,) + params
            ).fetchall()
        return [r["username"] for r in rows]
    finally:
        conn.close()


def list_tg_sources():
    """返回 tg_contacts 中所有非空 distinct source（用于发送页下拉）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT source FROM tg_contacts"
            " WHERE source IS NOT NULL AND source != ''"
            " ORDER BY source"
        ).fetchall()
        return [r["source"] for r in rows]
    finally:
        conn.close()


def list_x_sources():
    """返回 x_links 中所有非空 distinct source（用于发送页下拉）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT source FROM x_links"
            " WHERE source IS NOT NULL AND source != ''"
            " ORDER BY source"
        ).fetchall()
        return [r["source"] for r in rows]
    finally:
        conn.close()


# ─── Skip Handle ─────────────────────────────────────────────
def skip_handle(username, reason="ocr_no_match"):
    """标记 tg_contacts 中的 handle 为跳过，不从队列删除"""
    result = _api_post("skip", {"username": username, "reason": reason})
    if result is not None:
        return
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE tg_contacts SET skip_reason=?, skipped_at=CURRENT_TIMESTAMP WHERE username=?",
            (reason, username)
        )
        conn.commit()
    finally:
        conn.close()


def get_skipped_handles():
    """查询所有被跳过的 handle"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT username, skip_reason, skipped_at, source"
            " FROM tg_contacts WHERE skip_reason IS NOT NULL"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def unskip_handle(username):
    """恢复被跳过的 handle，重新进入发送队列"""
    result = _api_post("unskip", {"username": username})
    if result is not None:
        return
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE tg_contacts SET skip_reason=NULL, skipped_at=NULL WHERE username=?",
            (username,)
        )
        conn.commit()
    finally:
        conn.close()


def delete_tg_handle(username):
    """删除 tg_contacts 中 source='parsed' 的指定 handle（tg_left 不删）"""
    conn = get_conn()
    try:
        cursor = conn.execute(
            "DELETE FROM tg_contacts WHERE username=? AND source='parsed'",
            (username,)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def delete_tg_left_user(username):
    """删除 tg_contacts 中 source='tg_left' 的指定 handle"""
    conn = get_conn()
    try:
        cursor = conn.execute(
            "DELETE FROM tg_contacts WHERE username=? AND source='tg_left'",
            (username,)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def delete_bot_handles():
    """删除 tg_contacts 中所有以 'bot' 结尾的 handle，返回 (total, parsed, tg_left)"""
    conn = get_conn()
    try:
        cursor1 = conn.execute(
            "DELETE FROM tg_contacts WHERE source='parsed' AND LOWER(username) LIKE '%bot'"
        )
        parsed_deleted = cursor1.rowcount
        cursor2 = conn.execute(
            "DELETE FROM tg_contacts WHERE source='tg_left' AND LOWER(username) LIKE '%bot'"
        )
        left_deleted = cursor2.rowcount
        conn.commit()
        return parsed_deleted + left_deleted, parsed_deleted, left_deleted
    finally:
        conn.close()


# ─── Send Log ─────────────────────────────────────────────────
def log_send(handle, channel, source, message_name):
    # 始终走 API（服务器和客户端都必须通过服务器记录发送）
    result = _api_post("log_send", {
        "handle": handle, "channel": channel,
        "source": source, "message_name": message_name
    })
    if result is not None:  # API 模式
        return
    # 回退本机 SQLite
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO send_log (handle, channel, source, message_name) VALUES (?,?,?,?)",
            (handle, channel, source, message_name)
        )
        conn.commit()
    finally:
        conn.close()


def get_send_log(channel=None, limit=200):
    conn = get_conn()
    try:
        if channel and channel != "all":
            rows = conn.execute(
                "SELECT * FROM send_log WHERE channel=? ORDER BY sent_at DESC LIMIT ?",
                (channel, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM send_log ORDER BY sent_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_send_log():
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM send_log").fetchone()[0]
    finally:
        conn.close()


# ─── Message Templates ────────────────────────────────────────
def save_template(channel, name, content):
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM message_templates WHERE channel=? AND name=?",
            (channel, name)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE message_templates SET content=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (content, existing["id"])
            )
        else:
            conn.execute(
                "INSERT INTO message_templates (channel, name, content) VALUES (?,?,?)",
                (channel, name, content)
            )
        conn.commit()
    finally:
        conn.close()


def set_active_template(channel, name):
    conn = get_conn()
    try:
        conn.execute("UPDATE message_templates SET is_active=0 WHERE channel=?", (channel,))
        conn.execute(
            "UPDATE message_templates SET is_active=1 WHERE channel=? AND name=?",
            (channel, name)
        )
        conn.commit()
    finally:
        conn.close()


def get_active_template(channel):
    result = _api_get(f"template/active/{channel}")
    if result is not None:
        return result
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT content, name FROM message_templates WHERE channel=? AND is_active=1",
            (channel,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_templates(channel):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, content, is_active, updated_at FROM message_templates WHERE channel=? ORDER BY id",
            (channel,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_template(template_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM message_templates WHERE id=?", (template_id,))
        conn.commit()
    finally:
        conn.close()


# ─── Settings ────────────────────────────────────────────────
def get_setting(key, default=None):
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def save_setting(key, value):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
            (key, str(value))
        )
        conn.commit()
    finally:
        conn.close()


def get_tg_credentials(purpose):
    """
    读取指定用途的 TG API 凭证。
    purpose: 'parser'（群管理员解析）| 'left'（离群用户扫描）| 'sender'（DM发送）
    未配置时回退到 config.py 中的默认值。
    返回 (api_id:int, api_hash:str, session_path:str)
    """
    api_id   = get_setting(f"tg_{purpose}_api_id",
                           str(_config.TG_API_ID))
    api_hash = get_setting(f"tg_{purpose}_api_hash",
                           _config.TG_API_HASH)
    session  = os.path.join(_config.DATA_DIR, f"tg_session_{purpose}")
    return int(api_id), api_hash, session


def save_tg_credentials(purpose, api_id, api_hash):
    """保存指定用途的 TG API 凭证"""
    save_setting(f"tg_{purpose}_api_id",  str(api_id).strip())
    save_setting(f"tg_{purpose}_api_hash", api_hash.strip())


def get_tg_search_pos():
    """返回 TG 搜索栏坐标 (x, y)，默认 config 中的值"""
    result = _api_get("setting/tg_search_pos")
    if result is not None:
        return result["x"], result["y"]
    x = int(get_setting("tg_search_bar_x", str(_config.TG_SEARCH_BAR_POS[0])))
    y = int(get_setting("tg_search_bar_y", str(_config.TG_SEARCH_BAR_POS[1])))
    return x, y


def save_tg_search_pos(x, y):
    save_setting("tg_search_bar_x", str(int(x)))
    save_setting("tg_search_bar_y", str(int(y)))


def get_send_check_region():
    """返回发送后错误检测的截图区域。未配置时动态取屏幕中间 1/2。"""
    result = _api_get("setting/send_check_region")
    if result is not None and result.get("top") is not None:
        return result
    top    = get_setting("send_check_top",    None)
    left   = get_setting("send_check_left",   None)
    width  = get_setting("send_check_width",  None)
    height = get_setting("send_check_height", None)
    if all(v is not None for v in [top, left, width, height]):
        return {"top": int(top), "left": int(left),
                "width": int(width), "height": int(height)}
    try:
        import pyautogui
        sw, sh = pyautogui.size()
    except Exception:
        sw, sh = 1920, 1080
    return {"top": sh // 4, "left": 0, "width": sw, "height": sh // 2}


def save_send_check_region(top, left, width, height):
    save_setting("send_check_top",    str(int(top)))
    save_setting("send_check_left",   str(int(left)))
    save_setting("send_check_width",  str(int(width)))
    save_setting("send_check_height", str(int(height)))


def get_ocr_region():
    """返回 OCR 截图区域 dict，键：top/left/width/height"""
    result = _api_get("setting/ocr_region")
    if result is not None:
        return result
    return {
        "top":    int(get_setting("ocr_region_top",    "80")),
        "left":   int(get_setting("ocr_region_left",   "0")),
        "width":  int(get_setting("ocr_region_width",  "400")),
        "height": int(get_setting("ocr_region_height", "800")),
    }


def save_ocr_region(top, left, width, height):
    save_setting("ocr_region_top",    str(int(top)))
    save_setting("ocr_region_left",   str(int(left)))
    save_setting("ocr_region_width",  str(int(width)))
    save_setting("ocr_region_height", str(int(height)))


def get_cooldown_hours():
    """返回冷却总小时数（0 = 关闭冷却，历史发送过的永不再发）"""
    result = _api_get("setting/cooldown")
    if result is not None:
        return result.get("total_hours", 0)
    try:
        days  = int(get_setting("cooldown_days",  "0"))
        hours = int(get_setting("cooldown_hours", "0"))
        return days * 24 + hours
    except (TypeError, ValueError):
        return 0


def _cooldown_clause(channel, col="handle"):
    """
    根据冷却设置返回 (sql_fragment, params) 元组。
    col    : 外层表中与 send_log.handle 对应的列名（handle 或 username）
    冷却=0 : 排除所有历史发送（永不重发）
    冷却>0 : 只排除冷却期内发送过的（冷却期后可再次触达）
    """
    cooldown = get_cooldown_hours()
    if cooldown == 0:
        return (
            f"{col} NOT IN (SELECT handle FROM send_log WHERE channel=?)",
            (channel,)
        )
    else:
        return (
            f"{col} NOT IN ("
            f"  SELECT handle FROM send_log"
            f"  WHERE channel=?"
            f"  AND sent_at > datetime('now', ? || ' hours')"
            f")",
            (channel, f"-{cooldown}")
        )


# ─── Dashboard Stats ──────────────────────────────────────────
def get_stats():
    result = _api_get("stats")
    if result is not None:
        return result
    return {
        "projects":      count_projects(),
        "tg_links":      count_tg_links(),
        "x_links":       count_x_links(),
        "tg_handles":    count_tg_handles(),
        "tg_left_users": count_tg_left_users(),
        "sent_total":    count_send_log(),
        "tg_pending":    len(get_unsent_tg_by_source(None)),
        "x_pending":     len(get_unsent_x_handles()),
    }
