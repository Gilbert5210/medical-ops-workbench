import asyncio
import csv
import hashlib
import io
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import ai, xhs, topics
from .cards import bundle_hash, card_html
from .db import DATA, ROOT, Audience, Draft, Job, Report, Session, Source, initialize, now, setting, set_setting
from .services import approve, enqueue, import_sources, invalidate_approval, metrics, serialize


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title="科研运营工作台", lifespan=lifespan, docs_url="/api/docs", redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])


@app.middleware("http")
async def local_only(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin", "")
        host = request.headers.get("host", "")
        if origin and urlparse(origin).netloc != host:
            return JSONResponse({"detail": "仅接受工作台本机页面的请求。"}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "拒绝跨站请求。"}, status_code=403)
        if "application/json" not in request.headers.get("content-type", ""):
            return JSONResponse({"detail": "请使用JSON提交。"}, status_code=415)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    if request.url.path.startswith("/api/") and "/card/" not in request.url.path:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'self'"
    return response


@app.exception_handler(IntegrityError)
async def integrity_handler(request, exc):
    return JSONResponse({"detail": "这份稿件已创建发布任务，请勿重复提交。"}, status_code=409)


@app.exception_handler(ValueError)
async def value_handler(request, exc):
    return JSONResponse({"detail": str(exc)[:400]}, status_code=400)


@app.exception_handler(ai.ModelError)
@app.exception_handler(xhs.ConnectorError)
async def connection_handler(request, exc):
    return JSONResponse({"detail": str(exc)[:400]}, status_code=400)


def require(s, model, item_id):
    row = s.get(model, item_id)
    if not row:
        raise HTTPException(404, "未找到记录。")
    return row


def source_public(row):
    data = serialize(row)
    data["meta"] = {k: v for k, v in row.meta.items() if k != "xsec_token"}
    return data


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/overview")
def overview(days: int = 30):
    with Session() as s:
        return metrics(s, max(1, min(days, 365)))


@app.get("/api/audiences")
def audiences():
    with Session() as s:
        return [serialize(a) for a in s.scalars(select(Audience).order_by(Audience.id))]


@app.get("/api/sources")
def sources(q: str = "", audience_id: str = "", limit: int = 200):
    with Session() as s:
        query = select(Source).order_by(Source.id.desc()).limit(max(1, min(limit, 500)))
        if q:
            query = query.where(Source.text.contains(q, autoescape=True))
        if audience_id:
            query = query.where(Source.audience_id == audience_id)
        return [source_public(a) for a in s.scalars(query)]


class ImportBody(BaseModel):
    items: list[dict] = Field(min_length=1, max_length=200)


@app.post("/api/sources/import")
def import_data(body: ImportBody):
    with Session.begin() as s:
        return {"added": import_sources(s, body.items)}


class RawImportBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000000)
    url: str = Field(default="", max_length=2000)


@app.post("/api/sources/import-text")
def import_text(body: RawImportBody):
    text = body.text.lstrip("\ufeff").strip()
    if text.startswith("["):
        try:
            items = json.loads(text)
        except ValueError:
            raise ValueError("JSON格式不正确。") from None
        if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
            raise ValueError("请提供包含text字段的JSON对象数组。")
    elif "text" in next(csv.reader(io.StringIO(text)), []):
        items = list(csv.DictReader(io.StringIO(text)))
    else:
        items = [{"text": t, "url": body.url} for t in re.split(r"\n\s*\n", text) if t.strip()]
    if len(items) > 200:
        raise ValueError("每批最多导入200条素材。")
    with Session.begin() as s:
        return {"added": import_sources(s, items)}


class IdsBody(BaseModel):
    source_ids: list[int] = Field(default_factory=list, max_length=30)


@app.post("/api/sources/analyze")
def analyze_data(body: IdsBody):
    with Session.begin() as s:
        return serialize(enqueue(s, "analyze", body.model_dump()))


class CollectBody(BaseModel):
    keyword: str = Field(min_length=1, max_length=80)
    limit: int = Field(default=10, ge=1, le=20)


class TopicBody(BaseModel):
    audience_id: str
    content_type: Literal["A", "B", "C"] = "A"


@app.get("/api/discovery/topics")
def discovery_topics(audience_id: str = "M01", content_type: Literal["A", "B", "C"] = "A"):
    with Session() as s:
        audience = require(s, Audience, audience_id)
        return topics.snapshot(s, audience, content_type)


@app.post("/api/discovery/topics")
async def refresh_discovery_topics(body: TopicBody):
    # One request per audience/type while pending; old successful results remain usable.
    with Session.begin() as s:
        require(s, Audience, body.audience_id)
        last, _, active = topics.latest(s, body.audience_id, body.content_type)
        if active:
            return serialize(active)
        if last and datetime.now(timezone.utc) - datetime.fromisoformat(last.created_at) < timedelta(minutes=1):
            raise ValueError("这组人群刚刚刷新过，请稍后再试；已有推荐仍可使用。")
        return serialize(enqueue(s, "recommend_topics", body.model_dump()))


@app.post("/api/sources/search")
def collect_data(body: CollectBody):
    with Session.begin() as s:
        return serialize(enqueue(s, "collect", body.model_dump()))


@app.post("/api/sources/{source_id}/comments")
def collect_comments(source_id: int):
    with Session.begin() as s:
        row = require(s, Source, source_id)
        if row.kind != "note":
            raise ValueError("只能读取小红书笔记的评论。")
        return serialize(enqueue(s, "collect", {"source_id": source_id}))


@app.get("/api/sources/export")
def export_sources():
    output = io.StringIO()
    fields = ["id", "kind", "title", "text", "url", "audience_id", "task", "intent", "summary", "evidence", "created_at"]
    writer = csv.DictWriter(output, fields, extrasaction="ignore")
    writer.writeheader()
    with Session() as s:
        for row in s.scalars(select(Source).order_by(Source.id)):
            data = serialize(row)
            for key in fields:
                if isinstance(data.get(key), str) and data[key].lstrip().startswith(("=", "+", "-", "@")):
                    data[key] = "'" + data[key]
            writer.writerow(data)
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="sources.csv"'})


class GenerateBody(BaseModel):
    audience_id: str
    content_type: Literal["A", "B", "C"] = "A"
    topic: str = Field(default="", max_length=1000)
    source_ids: list[int] = Field(default_factory=list, max_length=10)


@app.post("/api/drafts/generate")
def generate_draft(body: GenerateBody):
    with Session.begin() as s:
        require(s, Audience, body.audience_id)
        return serialize(enqueue(s, "generate", body.model_dump()))


@app.get("/api/drafts")
def drafts():
    with Session() as s:
        return [serialize(a) for a in s.scalars(select(Draft).order_by(Draft.id.desc()).limit(200))]


@app.get("/api/drafts/{draft_id}")
def get_draft(draft_id: int):
    with Session() as s:
        return serialize(require(s, Draft, draft_id))


class DraftBody(BaseModel):
    version: int
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=6000)
    tags: list[str] = Field(default_factory=list, max_length=8)
    cards: list[dict] = Field(min_length=1, max_length=9)


@app.put("/api/drafts/{draft_id}")
def save_draft(draft_id: int, body: DraftBody):
    with Session.begin() as s:
        row = require(s, Draft, draft_id)
        if row.version != body.version:
            raise HTTPException(409, "稿件已更新，请刷新后再编辑。")
        if row.state == "published":
            raise ValueError("已发布的稿件请创建副本后修改。")
        invalidate_approval(s, row)
        from .worker import CardOutput
        from pydantic import ValidationError
        try:
            cards = [CardOutput.model_validate(card).model_dump() for card in body.cards]
        except ValidationError:
            raise ValueError("图卡标题最多50字、正文最多250字，均不能为空。") from None
        row.title, row.body, row.tags, row.cards = body.title, body.body, [str(t)[:50] for t in body.tags], cards
        row.version += 1
        row.updated_at = now()
        return serialize(row)


@app.post("/api/drafts/{draft_id}/duplicate")
def duplicate_draft(draft_id: int):
    with Session.begin() as s:
        row = require(s, Draft, draft_id)
        copied = Draft(**{key: getattr(row, key) for key in ("audience_id", "content_type", "title", "body", "tags", "cards", "checks", "source_ids", "platform")})
        s.add(copied)
        s.flush()
        return serialize(copied)


@app.get("/api/drafts/{draft_id}/card/{index}")
def preview_card(draft_id: int, index: int):
    with Session() as s:
        draft = require(s, Draft, draft_id)
        if index < 0 or index >= len(draft.cards):
            raise HTTPException(404)
        return HTMLResponse(card_html(draft, index))


class ApprovalBody(BaseModel):
    version: int
    account_id: str = Field(min_length=1)
    schedule_at: str
    reviewed: bool


@app.post("/api/drafts/{draft_id}/approve")
def approve_draft(draft_id: int, body: ApprovalBody):
    if not body.reviewed:
        raise ValueError("请先核对完整正文、图卡、账号和时间。")
    with Session.begin() as s:
        account = setting(s, "account")
        if account.get("id") != body.account_id:
            raise ValueError("请先在设置中核验小红书账号。")
        verified = datetime.fromisoformat(account["verified_at"])
        if datetime.now(timezone.utc) - verified > timedelta(hours=12):
            raise ValueError("账号核验已超过12小时，请重新核验。")
        row = require(s, Draft, draft_id)
        approve(s, row, body.version, body.account_id, account["name"], body.schedule_at)
        return serialize(row)


@app.get("/api/jobs")
def jobs():
    with Session() as s:
        return [serialize(j) for j in s.scalars(select(Job).order_by(Job.id.desc()).limit(100))]


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    with Session.begin() as s:
        job = require(s, Job, job_id)
        if job.state not in ("pending", "waiting"):
            raise ValueError("任务已经执行，不能在本地取消；已提交预约请到平台后台取消。")
        job.state, job.finished_at = "cancelled", now()
        if job.kind == "publish":
            row = require(s, Draft, job.payload["draft_id"])
            row.state, row.approval = "needs_review", {}
            row.version += 1
        return serialize(job)


class RetryBody(BaseModel):
    confirmed: bool
    publish_now: bool = False


@app.post("/api/jobs/{job_id}/retry")
def retry_publish(job_id: int, body: RetryBody):
    if not body.confirmed:
        raise ValueError("请确认重试方式后再提交。")
    with Session.begin() as s:
        job = require(s, Job, job_id)
        if job.kind != "publish" or job.state != "rejected":
            raise ValueError("只有明确未提交到平台的任务可以重试；结果不明时请先核对后台。")
        draft = require(s, Draft, job.payload["draft_id"])
        if draft.state != "rejected" or draft.version != job.payload.get("version") or bundle_hash(draft) != job.payload.get("hash"):
            raise ValueError("稿件已修改，请重新审核最新版本。")
        previous = {"state": job.state, "error": job.error, "finished_at": job.finished_at, "schedule_at": job.payload["schedule_at"]}
        approval = {k: job.payload[k] for k in ("version", "hash", "account_id", "account_name", "schedule_at", "approved_at")}
        if body.publish_now:
            approval["schedule_at"] = now()
        approval["approved_at"] = now()
        history = job.payload.get("history", []) + [previous]
        draft.approval, draft.state, draft.updated_at = approval, "approved", now()
        job.payload = {"draft_id": draft.id, **approval, "history": history, "attempt": job.payload.get("attempt", 1) + 1}
        job.state, job.error, job.result = "pending", "", {}
        job.started_at, job.finished_at = "", ""
        return serialize(job)


class ConfirmBody(BaseModel):
    state: Literal["scheduled", "published", "not_published"]
    url: str = Field(default="", max_length=2000)
    note: str = Field(min_length=1, max_length=500)


@app.post("/api/jobs/{job_id}/confirm")
def confirm_publish(job_id: int, body: ConfirmBody):
    with Session.begin() as s:
        job = require(s, Job, job_id)
        if job.kind != "publish" or job.state not in ("submitted", "unknown", "scheduled"):
            raise ValueError("该任务暂不适用人工核对。")
        if body.url and not re.match(r"^https://(?:www\.)?(?:xiaohongshu\.com|xhslink\.com)/", body.url):
            raise ValueError("请填写小红书结果链接。")
        job.state = body.state
        job.result = {**job.result, "manual_confirmation": body.model_dump(), "confirmed_at": now()}
        draft = require(s, Draft, job.payload["draft_id"])
        draft.state = {"scheduled": "submitted", "published": "published", "not_published": "needs_review"}[body.state]
        if body.state == "not_published":
            draft.approval = {}
            # A new version is required before another publishing attempt.
            draft.version += 1
        return serialize(job)


class ReportBody(BaseModel):
    days: int = Field(default=30, ge=1, le=365)


@app.post("/api/reports")
def create_report(body: ReportBody):
    with Session.begin() as s:
        return serialize(enqueue(s, "report", body.model_dump()))


@app.get("/api/reports")
def get_reports():
    with Session() as s:
        return [serialize(r) for r in s.scalars(select(Report).order_by(Report.id.desc()).limit(50))]


@app.get("/api/settings")
def settings():
    with Session() as s:
        return {"model": ai.public_config(), "connector": setting(s, "connector", {"url": "http://127.0.0.1:18060"}), "account": setting(s, "account"), "daily": setting(s, "daily", {"enabled": False, "time": "09:00", "audience_id": "M01", "content_type": "A"})}


class ModelBody(BaseModel):
    source: Literal["codex", "custom"]
    base_url: str = ""
    model: str = ""
    api_mode: Literal["responses", "chat"] = "responses"
    key: str = Field(default="", max_length=1000)


@app.put("/api/settings/model")
def save_model(body: ModelBody):
    if body.source == "custom":
        ai.validate_url(body.base_url)
        if not body.model.strip():
            raise ValueError("请填写模型名称。")
        if body.key:
            import keyring
            try:
                keyring.set_password("medical-ops-workbench", "model-key", body.key)
            except Exception:
                raise ValueError("系统钥匙串保存失败，请检查权限；密钥没有写入普通文件。") from None
    with Session.begin() as s:
        set_setting(s, "model", body.model_dump(exclude={"key"}))
    return ai.public_config()


@app.post("/api/settings/model/test")
async def test_model():
    output, usage = await ai.complete('连接测试。请只输出JSON：{"ok":true,"message":"模型连接正常"}')
    if output.get("ok") is not True:
        raise ValueError("模型已响应，但未通过结构化输出检查。")
    return {"ok": True, "message": "模型连接及结构化输出正常。", "usage": usage}


class ConnectorBody(BaseModel):
    url: str


@app.put("/api/settings/connector")
def save_connector(body: ConnectorBody):
    p = urlparse(body.url)
    if p.scheme != "http" or p.hostname not in ("127.0.0.1", "localhost") or p.path not in ("", "/") or p.query or p.fragment or p.username:
        raise ValueError("请填写本机连接地址，例如 http://127.0.0.1:18060")
    with Session.begin() as s:
        set_setting(s, "connector", {"url": body.url.rstrip("/")})
        set_setting(s, "account", {})
    return {"ok": True}


@app.get("/api/connector/status")
async def connector_status():
    return await xhs.status()


@app.post("/api/connector/check-publish")
async def check_publish_connection():
    async with xhs.BROWSER_LOCK:
        account = await xhs.identity()
        result = await xhs.request("GET", "/api/v1/login/creator-status", timeout=40)
    return {**result, "account": account}


@app.post("/api/connector/verify")
async def verify_account():
    async with xhs.BROWSER_LOCK:
        account = await xhs.identity()
        account["verified_at"] = now()
        with Session.begin() as s:
            set_setting(s, "account", account)
    return account


@app.post("/api/connector/logout")
async def logout_account():
    async with xhs.BROWSER_LOCK:
        with Session.begin() as s:
            if s.scalar(select(Job.id).where(Job.kind == "publish", Job.state == "running").limit(1)):
                raise ValueError("发布任务正在执行，请等任务结束后再切换账号。")
            # Revoke approval before touching login. Failures leave publishing disabled.
            set_setting(s, "account", {})
            cancelled = 0
            for job in s.scalars(select(Job).where(Job.kind == "publish", Job.state.in_(["pending", "waiting"]))):
                job.state, job.error, job.finished_at = "cancelled", "已切换账号，请核对新账号后重新审核稿件。", now()
                cancelled += 1
            for draft in s.scalars(select(Draft).where(Draft.state.in_(["approved", "rejected"]))):
                draft.state, draft.approval, draft.updated_at = "needs_review", {}, now()
                draft.version += 1
        await xhs.reset_login()
    return {"ok": True, "cancelled": cancelled, "message": "当前账号已退出，请用新账号扫码并核验。"}


@app.get("/api/connector/qrcode")
async def qrcode():
    async with xhs.BROWSER_LOCK:
        data = await xhs.request("GET", "/api/v1/login/qrcode", timeout=60)
    return {key: data.get(key) for key in ("img", "timeout", "is_logged_in")}


class DailyBody(BaseModel):
    enabled: bool
    time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    audience_id: str
    content_type: Literal["A", "B", "C"]


@app.put("/api/settings/daily")
def save_daily(body: DailyBody):
    with Session.begin() as s:
        require(s, Audience, body.audience_id)
        set_setting(s, "daily", body.model_dump())
    return {"ok": True}


DIST = ROOT / "frontend/dist"
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="frontend-assets")


@app.get("/{path:path}")
def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    if not (DIST / "index.html").exists():
        return HTMLResponse("前端尚未构建，请运行 npm run build。", status_code=503)
    return FileResponse(DIST / "index.html")
