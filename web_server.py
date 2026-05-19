"""
Web3 Outreach Hub — FastAPI 后端
提供 REST API + WebSocket（worker 实时日志）+ 静态文件服务
"""
import sys, os, json, asyncio, threading, shutil, tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── 路径 ──────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

import db
import config

# ══════════════════════════════════════════════════════════════════
#  FastAPI App
# ══════════════════════════════════════════════════════════════════
app = FastAPI(title="OutreachHub")

WEB_DIR = os.path.join(_ROOT, "web")

# ── WebSocket 管理 ────────────────────────────────────────────────
_ws_clients: set[WebSocket] = set()
_loop: Optional[asyncio.AbstractEventLoop] = None


@app.on_event("startup")
async def _grab_loop():
    global _loop
    _loop = asyncio.get_running_loop()


async def _broadcast(msg: dict):
    data = json.dumps(msg, ensure_ascii=False)
    for ws in list(_ws_clients):
        try:
            await ws.send_text(data)
        except Exception:
            _ws_clients.discard(ws)


def sync_broadcast(msg: dict):
    """从同步线程（worker）向所有 WS 客户端广播"""
    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(_broadcast(msg), _loop)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)


# ── Worker 管理 ───────────────────────────────────────────────────
_workers: dict = {}        # worker_id -> worker instance
_worker_threads: dict = {} # worker_id -> thread
_worker_events: dict = {}  # worker_id -> threading.Event (login/ready)
_upload_dir = os.path.join(_ROOT, "data", "_uploads")
os.makedirs(_upload_dir, exist_ok=True)


def _make_cbs(wid):
    """返回 (log_cb, progress_cb) 对"""
    def log_cb(msg):
        sync_broadcast({"type": "log", "worker": wid, "msg": msg})
    def progress_cb(cur, total=0):
        sync_broadcast({"type": "progress", "worker": wid, "cur": cur, "total": total})
    return log_cb, progress_cb


def _run_in_thread(wid, create_fn):
    """启动 worker 并在新线程中运行"""
    if wid in _workers:
        return {"error": "already_running"}
    log_cb, prog_cb = _make_cbs(wid)
    worker = create_fn(log_cb, prog_cb)
    _workers[wid] = worker

    def _run():
        sync_broadcast({"type": "started", "worker": wid})
        try:
            worker.run()
        except Exception as e:
            sync_broadcast({"type": "log", "worker": wid, "msg": f"[错误] {e}"})
        finally:
            _workers.pop(wid, None)
            _worker_threads.pop(wid, None)
            _worker_events.pop(wid, None)
            sync_broadcast({"type": "stopped", "worker": wid})

    t = threading.Thread(target=_run, daemon=True)
    _worker_threads[wid] = t
    t.start()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════
#  REST API
# ══════════════════════════════════════════════════════════════════

def ok(data=None):
    return {"code": 0, "data": data}

# ── Dashboard ─────────────────────────────────────────────────────
@app.get("/api/stats")
def api_stats():
    return ok(db.get_stats())


@app.get("/api/send-log")
def api_send_log(channel: str = "all", limit: int = 300):
    return ok(db.get_send_log(channel=channel, limit=limit))


# ── Counts ────────────────────────────────────────────────────────
@app.get("/api/counts")
def api_counts():
    return ok({
        "projects": db.count_projects(),
        "tg_links": db.count_tg_links(),
        "x_links": db.count_x_links(),
        "tg_handles": db.count_tg_handles(),
        "tg_left_users": db.count_tg_left_users(),
    })


# ── File Upload ───────────────────────────────────────────────────
@app.post("/api/upload/excel")
async def upload_excel(file: UploadFile = File(...)):
    dest = os.path.join(_upload_dir, file.filename)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return ok({"path": dest, "name": file.filename})


# ── Worker Start / Stop ──────────────────────────────────────────
class WorkerStartBody(BaseModel):
    params: dict = {}


@app.post("/api/workers/{worker_id}/start")
def start_worker(worker_id: str, body: WorkerStartBody):
    p = body.params

    # source_tag 校验（仅对入库类 worker 必填）
    TAG_REQUIRED = {
        "cb_discover", "rootdata", "chainscope", "tokenfinder",
        "campaign_twitter", "campaign_kol", "cryptorank",
    }
    tag = (p.get("source_tag") or "").strip()
    if worker_id in TAG_REQUIRED:
        if not tag:
            return JSONResponse(
                {"code": 1, "msg": "source_tag 必填（本批次分组标签）"}, 400)
        if tag == "tg_left":
            return JSONResponse(
                {"code": 1, "msg": "source_tag 不能为保留值 'tg_left'"}, 400)

    if worker_id == "scraper":
        from workers.scraper_worker import ScraperWorker
        use_llm = p.get("use_llm", False)
        concurrency = int(p.get("concurrency", 5))
        return ok(_run_in_thread(worker_id,
            lambda log, prog: ScraperWorker(log, prog, use_llm=use_llm, concurrency=concurrency)))

    if worker_id == "cb_discover":
        from workers.crunchbase_discover_worker import CrunchbaseDiscoverWorker
        url = p.get("url", "")
        evt = threading.Event()
        _worker_events[worker_id] = evt
        return ok(_run_in_thread(worker_id,
            lambda log, prog: CrunchbaseDiscoverWorker(
                start_url=url, source_tag=tag,
                log_callback=log, progress_callback=prog, login_event=evt)))

    if worker_id == "rootdata":
        from workers.rootdata_worker import RootDataWorker
        url = p.get("url", "https://www.rootdata.com/fundraising")
        max_pages = int(p.get("max_pages", 314))
        start_page = int(p.get("start_page", 1))
        return ok(_run_in_thread(worker_id,
            lambda log, prog: RootDataWorker(
                source_tag=tag, log_callback=log, progress_callback=prog,
                start_url=url, max_pages=max_pages, start_page=start_page)))

    if worker_id == "chainscope":
        from workers.chainscope_worker import ChainScopeWorker
        return ok(_run_in_thread(worker_id,
            lambda log, prog: ChainScopeWorker(tag, log, prog)))

    if worker_id == "tokenfinder":
        from workers.token_finder_worker import TokenFinderWorker
        return ok(_run_in_thread(worker_id,
            lambda log, prog: TokenFinderWorker(tag, log, prog)))

    if worker_id == "campaign_twitter":
        from workers.campaign_worker import CampaignWorker
        return ok(_run_in_thread(worker_id,
            lambda log, prog: CampaignWorker(
                endpoint="/api/projects", field="twitter_handle",
                strip_at=True, source_tag=tag,
                log_callback=log, progress_callback=prog)))

    if worker_id == "campaign_kol":
        from workers.campaign_worker import CampaignWorker
        return ok(_run_in_thread(worker_id,
            lambda log, prog: CampaignWorker(
                endpoint="/api/kol-projects", field="project_handle",
                strip_at=False, source_tag=tag,
                log_callback=log, progress_callback=prog)))

    if worker_id == "cryptorank":
        from workers.cryptorank_worker import CryptoRankWorker
        url = p.get("url", "https://cryptorank.io/funding-rounds?page=1&rows=20")
        max_pages = int(p.get("max_pages", 999))
        return ok(_run_in_thread(worker_id,
            lambda log, prog: CryptoRankWorker(
                source_tag=tag, log_callback=log, progress_callback=prog,
                start_url=url, max_pages=max_pages)))

    if worker_id == "parser":
        from workers.parser_worker import ParserWorker
        return ok(_run_in_thread(worker_id,
            lambda log, prog: ParserWorker(log, prog)))

    if worker_id == "tgleft":
        from workers.tgleft_worker import TGLeftWorker
        mm = int(p.get("max_members", config.TGLEFT_MAX_MEMBERS))
        ms = int(p.get("max_messages", config.TGLEFT_MAX_MESSAGES))
        return ok(_run_in_thread(worker_id,
            lambda log, prog: TGLeftWorker(log, prog, mm, ms)))

    if worker_id == "tg_sender":
        if sys.platform == 'darwin':
            from workers.tg_sender_web_worker import TGSenderWebWorker as TGSenderWorker
        else:
            from workers.tg_sender_worker import TGSenderWorker
        return ok(_run_in_thread(worker_id,
            lambda log, prog: TGSenderWorker(
                log, prog,
                p.get("source", "all"),
                int(p.get("max_per_hour", config.TG_MAX_PER_HOUR)),
                p.get("message_name", ""), p.get("message_content", ""))))

    if worker_id == "x_sender":
        if sys.platform == 'darwin':
            from workers.x_sender_pw_worker import XSenderPWWorker as XSenderWorker
        else:
            from workers.x_sender_worker import XSenderWorker
        return ok(_run_in_thread(worker_id,
            lambda log, prog: XSenderWorker(
                log, prog,
                p.get("message_name", ""), p.get("message_content", ""),
                p.get("source"))))

    if worker_id == "email_sender":
        from workers.email_sender_worker import EmailSenderWorker
        return ok(_run_in_thread(worker_id,
            lambda log, prog: EmailSenderWorker(
                log, prog,
                p.get("message_name", ""),
                p.get("subject", ""),
                p.get("body", ""),
                p.get("source"),
                int(p.get("daily_limit", 50)),
                int(p.get("interval_min", 30)),
                int(p.get("interval_max", 60)))))

    return JSONResponse({"code": 1, "msg": f"unknown worker: {worker_id}"}, 400)


@app.post("/api/workers/{worker_id}/stop")
def stop_worker(worker_id: str):
    w = _workers.get(worker_id)
    if w:
        w.stop()
        return ok({"stopped": True})
    return ok({"stopped": False, "msg": "not running"})


@app.post("/api/workers/{worker_id}/ready")
def worker_ready(worker_id: str):
    """CrunchbaseDiscover / RootData 的 '已就绪' 信号"""
    evt = _worker_events.get(worker_id)
    if evt:
        evt.set()
        return ok({"signaled": True})
    w = _workers.get(worker_id)
    if w and hasattr(w, "set_ready"):
        w.set_ready()
        return ok({"signaled": True})
    return ok({"signaled": False})


@app.get("/api/workers/status")
def workers_status():
    return ok({wid: True for wid in _workers})


@app.get("/api/platform")
def get_platform():
    return ok({"platform": sys.platform})


# ── Templates ─────────────────────────────────────────────────────
@app.get("/api/templates/{channel}")
def get_templates(channel: str):
    return ok(db.get_templates(channel))


class TemplateSaveBody(BaseModel):
    name: str
    content: str

@app.post("/api/templates/{channel}")
def save_template(channel: str, body: TemplateSaveBody):
    db.save_template(channel, body.name, body.content)
    return ok()


class TemplateActivateBody(BaseModel):
    name: str

@app.put("/api/templates/{channel}/activate")
def activate_template(channel: str, body: TemplateActivateBody):
    db.set_active_template(channel, body.name)
    return ok()


@app.get("/api/templates/{channel}/active")
def get_active_template(channel: str):
    return ok(db.get_active_template(channel))


@app.delete("/api/templates/{tid}")
def delete_template(tid: int):
    db.delete_template(tid)
    return ok()


# ── Settings ──────────────────────────────────────────────────────
class CooldownBody(BaseModel):
    days: int = 0
    hours: int = 0

@app.get("/api/settings/cooldown")
def get_cooldown():
    d = int(db.get_setting("cooldown_days", "0"))
    h = int(db.get_setting("cooldown_hours", "0"))
    return ok({"days": d, "hours": h})

@app.post("/api/settings/cooldown")
def save_cooldown(body: CooldownBody):
    db.save_setting("cooldown_days", str(body.days))
    db.save_setting("cooldown_hours", str(body.hours))
    return ok()


class TGCredBody(BaseModel):
    api_id: str
    api_hash: str

@app.get("/api/settings/tg-credentials/{purpose}")
def get_tg_creds(purpose: str):
    aid, ahash, _ = db.get_tg_credentials(purpose)
    return ok({"api_id": str(aid), "api_hash": ahash})

@app.post("/api/settings/tg-credentials/{purpose}")
def save_tg_creds(purpose: str, body: TGCredBody):
    db.save_tg_credentials(purpose, body.api_id, body.api_hash)
    return ok()


# ── Sources (distinct source tags) ────────────────────────────────
@app.get("/api/sources/tg")
def api_sources_tg():
    return ok(db.list_tg_sources())


@app.get("/api/sources/x")
def api_sources_x():
    return ok(db.list_x_sources())


# ── Queue Preview ─────────────────────────────────────────────────
@app.get("/api/queue/preview")
def queue_preview():
    return ok({
        "tg_imported": len(db.get_unsent_tg_imported_handles()),
        "tg_parsed":   len(db.get_unsent_tg_parsed_handles()),
        "tg_left":     len(db.get_unsent_tg_left_handles()),
        "x":           len(db.get_unsent_x_handles()),
    })


# ── DeepSeek ──────────────────────────────────────────────────────
@app.get("/api/settings/deepseek-key")
def get_deepseek_key():
    raw = db.get_setting("deepseek_api_key", "")
    keys = [k.strip() for k in raw.replace('\n', ',').split(',') if k.strip()]
    masked = ", ".join(k[:8] + "***" for k in keys) if keys else ""
    return ok({"masked": masked, "exists": bool(keys), "count": len(keys)})

class DeepSeekBody(BaseModel):
    key: str

@app.post("/api/settings/deepseek-key")
def save_deepseek_key(body: DeepSeekBody):
    db.save_setting("deepseek_api_key", body.key)
    return ok()


# ── Generic Setting (MUST be after all specific /api/settings/* routes) ──
class SettingBody(BaseModel):
    key: str
    value: str

@app.get("/api/settings/{key}")
def get_setting(key: str, default: str = ""):
    return ok({"value": db.get_setting(key, default)})

@app.post("/api/settings")
def save_setting(body: SettingBody):
    db.save_setting(body.key, body.value)
    return ok()


# ── Shutdown ──────────────────────────────────────────────────────
@app.post("/api/shutdown")
def shutdown():
    """退出整个进程（延迟 0.5s，确保响应先返回客户端）"""
    def _exit():
        import time
        time.sleep(0.5)
        os._exit(0)
    threading.Thread(target=_exit, daemon=True).start()
    return ok({"shutting_down": True})


# ── Static Files (Web UI) ────────────────────────────────────────
@app.get("/")
def serve_index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


# 挂载 web/ 静态资源（CSS/JS/图片等）
app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")
