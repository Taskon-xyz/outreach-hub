"""
SQLite REST API 服务器
供局域网内其他电脑（客户端）在发送模式下调用
所有数据库操作在本机完成，结果通过 JSON 返回
"""
import sqlite3
import os
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ── 数据库路径（相对于 server/ 的父目录，即 outreach-hub 根目录）───
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_ROOT, "data", "outreach.db")

write_lock = threading.Lock()


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ok(data=None, msg="ok"):
    return jsonify({"code": 0, "msg": msg, "data": data})


def api_err(msg="error"):
    return jsonify({"code": 1, "msg": msg}), 400


# ═══════════════════════════════════════════════════════════════
#  发送记录（最核心，必须走服务器）
# ═══════════════════════════════════════════════════════════════
@app.route("/api/log_send", methods=["POST"])
def api_log_send():
    """记录一条发送"""
    data = request.json or {}
    required = ["handle", "channel", "source"]
    for k in required:
        if not data.get(k):
            return api_err(f"missing field: {k}")

    with write_lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO send_log (handle, channel, source, message_name) VALUES (?,?,?,?)",
                (data["handle"], data["channel"], data["source"], data.get("message_name", ""))
            )
            conn.commit()
            return ok()
        except Exception as e:
            return api_err(str(e))
        finally:
            conn.close()


@app.route("/api/send_log/recent", methods=["GET"])
def api_send_log_recent():
    """最近发送记录（仪表盘用）"""
    limit = int(request.args.get("limit", 10))
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM send_log ORDER BY sent_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return ok([dict(r) for r in rows])
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  待发队列（冷却+去重在本机计算，客户端只拿结果）
# ═══════════════════════════════════════════════════════════════
def _cooldown_clause(conn, channel, col):
    cooldown = _get_cooldown_hours(conn)
    if cooldown == 0:
        return f"{col} NOT IN (SELECT handle FROM send_log WHERE channel=?)", (channel,)
    return (
        f"{col} NOT IN ("
        f"  SELECT handle FROM send_log"
        f"  WHERE channel=? AND sent_at > datetime('now',?||' hours')"
        f")",
        (channel, f"-{cooldown}")
    )


def _get_cooldown_hours(conn):
    rows = conn.execute(
        "SELECT key, value FROM settings WHERE key IN ('cooldown_days','cooldown_hours')"
    ).fetchall()
    vals = {r["key"]: int(r["value"]) for r in rows}
    return vals.get("cooldown_days", 0) * 24 + vals.get("cooldown_hours", 0)


@app.route("/api/queue/tg", methods=["GET"])
def api_queue_tg():
    """统一 TG 队列接口：?source=<tag> 过滤；留空或 'all' 返回全部（含 NULL）"""
    source = request.args.get("source")
    conn = get_conn()
    try:
        clause, params = _cooldown_clause(conn, "telegram", "username")
        if not source or source == "all":
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
        return ok([r["username"] for r in rows])
    finally:
        conn.close()


@app.route("/api/queue/tg/sources", methods=["GET"])
def api_queue_tg_sources():
    """返回 tg_contacts 中所有非空 distinct source"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT source FROM tg_contacts"
            " WHERE source IS NOT NULL AND source != ''"
            " ORDER BY source"
        ).fetchall()
        return ok([r["source"] for r in rows])
    finally:
        conn.close()


@app.route("/api/queue/tg_admin", methods=["GET"])
def api_queue_tg_admin():
    """（兼容旧调用方）tg_contacts 中 source != 'tg_left' 的全部"""
    conn = get_conn()
    try:
        clause, params = _cooldown_clause(conn, "telegram", "username")
        rows = conn.execute(
            f"SELECT username FROM tg_contacts"
            f" WHERE (source IS NULL OR source != 'tg_left')"
            f"   AND skip_reason IS NULL AND {clause}",
            params
        ).fetchall()
        return ok([r["username"] for r in rows])
    finally:
        conn.close()


@app.route("/api/queue/tg_imported", methods=["GET"])
def api_queue_tg_imported():
    """（兼容旧调用方）仅 source_link='google_sheet_import' 的仓库导入记录"""
    conn = get_conn()
    try:
        clause, params = _cooldown_clause(conn, "telegram", "username")
        rows = conn.execute(
            f"SELECT username FROM tg_contacts"
            f" WHERE source_link='google_sheet_import'"
            f"   AND skip_reason IS NULL AND {clause}",
            params
        ).fetchall()
        return ok([r["username"] for r in rows])
    finally:
        conn.close()


@app.route("/api/queue/tg_parsed", methods=["GET"])
def api_queue_tg_parsed():
    """（兼容旧调用方）群解析出来的 admin 记录（非仓库且非 tg_left）"""
    conn = get_conn()
    try:
        clause, params = _cooldown_clause(conn, "telegram", "username")
        rows = conn.execute(
            f"SELECT username FROM tg_contacts"
            f" WHERE (source_link IS NULL OR source_link!='google_sheet_import')"
            f"   AND (source IS NULL OR source != 'tg_left')"
            f"   AND skip_reason IS NULL AND {clause}",
            params
        ).fetchall()
        return ok([r["username"] for r in rows])
    finally:
        conn.close()


@app.route("/api/queue/tg_left", methods=["GET"])
def api_queue_tg_left():
    """离群用户（source='tg_left'）"""
    conn = get_conn()
    try:
        clause, params = _cooldown_clause(conn, "telegram", "username")
        rows = conn.execute(
            f"SELECT username FROM tg_contacts"
            f" WHERE source='tg_left' AND skip_reason IS NULL AND {clause}",
            params
        ).fetchall()
        return ok([r["username"] for r in rows])
    finally:
        conn.close()


@app.route("/api/queue/x", methods=["GET"])
def api_queue_x():
    """X handles，可选 source 过滤"""
    source = request.args.get("source")  # None = 全部
    conn = get_conn()
    try:
        clause, params = _cooldown_clause(conn, "twitter", "handle")
        if source:
            rows = conn.execute(
                f"SELECT handle FROM x_links WHERE source=? AND {clause}",
                (source,) + params
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT handle FROM x_links WHERE {clause}", params
            ).fetchall()
        return ok([r["handle"] for r in rows])
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  跳过 / 恢复
# ═══════════════════════════════════════════════════════════════
@app.route("/api/skip", methods=["POST"])
def api_skip():
    """标记用户跳过（tg_contacts 单表）"""
    data = request.json or {}
    username = (data.get("username") or data.get("handle") or "").strip()
    if not username:
        return api_err("username required")
    reason = data.get("reason", "manual_skip")

    with write_lock:
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE tg_contacts SET skip_reason=?, skipped_at=CURRENT_TIMESTAMP WHERE username=?",
                (reason, username)
            )
            conn.commit()
            return ok()
        except Exception as e:
            return api_err(str(e))
        finally:
            conn.close()


@app.route("/api/unskip", methods=["POST"])
def api_unskip():
    """恢复被跳过的用户（tg_contacts 单表）"""
    data = request.json or {}
    username = (data.get("username") or data.get("handle") or "").strip()
    if not username:
        return api_err("username required")

    with write_lock:
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE tg_contacts SET skip_reason=NULL, skipped_at=NULL WHERE username=?",
                (username,)
            )
            conn.commit()
            return ok()
        finally:
            conn.close()


# ═══════════════════════════════════════════════════════════════
#  文案模板
# ═══════════════════════════════════════════════════════════════
@app.route("/api/template/active/<channel>", methods=["GET"])
def api_active_template(channel):
    """获取当前激活的文案"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT content, name FROM message_templates WHERE channel=? AND is_active=1",
            (channel,)
        ).fetchone()
        return ok(dict(row) if row else None)
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  设置（发送相关）
# ═══════════════════════════════════════════════════════════════
@app.route("/api/setting/cooldown", methods=["GET"])
def api_cooldown():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key IN ('cooldown_days','cooldown_hours')"
        ).fetchall()
        vals = {r["key"]: int(r["value"]) for r in rows}
        return ok({
            "cooldown_days": vals.get("cooldown_days", 0),
            "cooldown_hours": vals.get("cooldown_hours", 0),
            "total_hours": vals.get("cooldown_days", 0) * 24 + vals.get("cooldown_hours", 0),
        })
    finally:
        conn.close()


@app.route("/api/setting/tg_search_pos", methods=["GET"])
def api_tg_search_pos():
    conn = get_conn()
    try:
        rows = dict(conn.execute(
            "SELECT key, value FROM settings WHERE key IN ('tg_search_bar_x','tg_search_bar_y')"
        ).fetchall())
        from config import TG_SEARCH_BAR_POS
        x = int(rows.get("tg_search_bar_x", TG_SEARCH_BAR_POS[0]))
        y = int(rows.get("tg_search_bar_y", TG_SEARCH_BAR_POS[1]))
        return ok({"x": x, "y": y})
    finally:
        conn.close()


@app.route("/api/setting/ocr_region", methods=["GET"])
def api_ocr_region():
    conn = get_conn()
    try:
        rows = dict(conn.execute(
            "SELECT key, value FROM settings WHERE key LIKE 'ocr_region_%'"
        ).fetchall())
        return ok({
            "top":    int(rows.get("ocr_region_top",    80)),
            "left":   int(rows.get("ocr_region_left",   0)),
            "width":  int(rows.get("ocr_region_width",  400)),
            "height": int(rows.get("ocr_region_height", 800)),
        })
    finally:
        conn.close()


@app.route("/api/setting/send_check_region", methods=["GET"])
def api_send_check_region():
    conn = get_conn()
    try:
        rows = dict(conn.execute(
            "SELECT key, value FROM settings WHERE key LIKE 'send_check_%'"
        ).fetchall())
        if rows.get("send_check_top") is not None:
            return ok({
                "top":    int(rows["send_check_top"]),
                "left":   int(rows["send_check_left"]),
                "width":  int(rows["send_check_width"]),
                "height": int(rows["send_check_height"]),
            })
        # 未配置时返回默认值（屏幕中间 1/2）
        return ok({"top": None, "left": None, "width": None, "height": None})
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  仪表盘统计
# ═══════════════════════════════════════════════════════════════
@app.route("/api/stats", methods=["GET"])
def api_stats():
    conn = get_conn()
    try:
        cooldown = _get_cooldown_hours(conn)
        clause_tg, p_tg = _cooldown_clause(conn, "telegram", "username")
        clause_x, p_x = _cooldown_clause(conn, "twitter", "handle")

        tg_admin_pending = conn.execute(
            f"SELECT COUNT(*) FROM tg_contacts"
            f" WHERE (source IS NULL OR source != 'tg_left')"
            f"   AND skip_reason IS NULL AND {clause_tg}", p_tg
        ).fetchone()[0]
        tg_left_pending = conn.execute(
            f"SELECT COUNT(*) FROM tg_contacts"
            f" WHERE source='tg_left' AND skip_reason IS NULL AND {clause_tg}", p_tg
        ).fetchone()[0]
        x_pending = conn.execute(
            f"SELECT COUNT(*) FROM x_links WHERE {clause_x}", p_x
        ).fetchone()[0]

        return ok({
            "projects":     conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
            "tg_links":     conn.execute("SELECT COUNT(*) FROM tg_links").fetchone()[0],
            "x_links":      conn.execute("SELECT COUNT(*) FROM x_links").fetchone()[0],
            "tg_handles":   conn.execute(
                "SELECT COUNT(*) FROM tg_contacts"
                " WHERE source IS NULL OR source != 'tg_left'"
            ).fetchone()[0],
            "tg_left_users":conn.execute(
                "SELECT COUNT(*) FROM tg_contacts WHERE source='tg_left'"
            ).fetchone()[0],
            "sent_total":   conn.execute("SELECT COUNT(*) FROM send_log").fetchone()[0],
            "tg_pending":   tg_admin_pending + tg_left_pending,
            "x_pending":    x_pending,
        })
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  健康检查
# ═══════════════════════════════════════════════════════════════
@app.route("/api/ping", methods=["GET"])
def api_ping():
    return ok({"status": "running", "db": DB_PATH})


# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000

    # 尝试导入 config 读取默认端口等配置
    try:
        sys.path.insert(0, _ROOT)
        import config as _cfg
        port = int(sys.argv[1]) if len(sys.argv) > 1 else getattr(_cfg, "API_PORT", 5000)
    except Exception:
        pass

    print(f"[OutreachHub API] 数据库: {DB_PATH}")
    print(f"[OutreachHub API] 监听: 0.0.0.0:{port}")
    print(f"[OutreachHub API] 局域网访问: http://<本机IP>:{port}/api/ping")

    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
