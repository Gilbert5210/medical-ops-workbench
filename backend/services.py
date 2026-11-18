import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .cards import bundle_hash
from .db import Audience, Draft, Job, Source, now


def serialize(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def enqueue(s, kind, payload, dedupe=None):
    job = Job(kind=kind, payload=payload, dedupe=dedupe)
    s.add(job)
    s.flush()
    return job


def metrics(s, days=30):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    sources = list(s.scalars(select(Source).where(Source.created_at >= cutoff)))
    drafts = list(s.scalars(select(Draft).where(Draft.created_at >= cutoff)))
    jobs = list(s.scalars(select(Job).where(Job.created_at >= cutoff)))
    audiences = {a.id: a.name for a in s.scalars(select(Audience))}
    by_audience = Counter(audiences.get(x.audience_id, "未知／待判断") for x in sources)
    by_task = Counter(x.task for x in sources)
    return {
        "days": days, "since": cutoff, "as_of": now(), "source_count": len(sources),
        "analyzed_count": sum(x.analyzed for x in sources), "draft_count": len(drafts),
        "review_count": sum(x.state == "needs_review" for x in drafts),
        "approved_count": sum(x.state == "approved" for x in drafts),
        "submitted_count": sum(x.kind == "publish" and x.state in ("submitted", "scheduled", "published") for x in jobs),
        "published_count": sum(x.kind == "publish" and x.state == "published" for x in jobs),
        "audiences": [{"name": k, "count": v} for k, v in by_audience.most_common(8)],
        "tasks": [{"name": k, "count": v} for k, v in by_task.most_common(8)],
        "kinds": dict(Counter(x.kind for x in sources)),
        "missing_metrics": ["曝光量", "阅读量", "有效咨询", "成交额"],
        "scope": "仅当前时间窗口内导入或采集的样本，不代表全站或市场总体；未采集指标不计为0。",
    }


def insert_source(s, *, external_id, kind, title, text, url="", keyword="", meta=None):
    existing = s.scalar(select(Source).where(Source.external_id == external_id))
    if existing:
        changed = existing.text != text
        existing.text, existing.title = text, title
        existing.url, existing.keyword = url, keyword
        existing.meta = {**existing.meta, **(meta or {}), "last_seen": now()}
        if changed:
            existing.analyzed = False
            existing.audience_id, existing.task, existing.intent = "", "待判断", "未知"
            existing.summary, existing.evidence, existing.confidence = "", "", "待分析"
        return existing, False
    item = Source(external_id=external_id, kind=kind, title=title, text=text, url=url, keyword=keyword, meta=meta or {})
    s.add(item)
    s.flush()
    return item, True


def import_sources(s, items):
    added = 0
    for item in items:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        if len(text) > 20000:
            raise ValueError("单条文本请控制在20000字以内。")
        url = str(item.get("url", ""))[:2000]
        ext = "manual:" + hashlib.sha256((url + "\n" + text).encode()).hexdigest()
        _, created = insert_source(s, external_id=ext, kind="manual", title=str(item.get("title", "手动导入"))[:300], text=text, url=url)
        added += created
    return added


def validate_schedule(value):
    try:
        target = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("预约时间格式不正确。") from None
    if not target.tzinfo:
        raise ValueError("预约时间必须包含时区。")
    return target.isoformat()


def delivery_plan(schedule_at, current=None):
    """Route around connector booking limits without restricting user dates."""
    target = datetime.fromisoformat(schedule_at)
    remaining = target - (current or datetime.now(timezone.utc))
    if remaining <= timedelta(0):
        return "immediate"
    # Buffer for rendering and identity checks; all other dates use the local queue.
    if timedelta(minutes=70) <= remaining <= timedelta(days=13):
        return "platform"
    return "local_wait"


def approve(s, draft, version, account_id, account_name, schedule_at):
    if draft.version != version:
        raise ValueError("稿件已更新，请刷新后审核最新版本。")
    if draft.platform != "小红书":
        raise ValueError("初版仅支持小红书发布。")
    if not draft.title.strip() or not draft.body.strip() or not draft.cards:
        raise ValueError("请补全标题、正文和图卡。")
    if len(draft.title) > 20 or len(draft.body) > 1000:
        raise ValueError("请将标题缩短至20字内、正文缩短至1000字内。")
    if draft.state in ("submitting", "submitted", "unknown", "published"):
        raise ValueError("该版本已进入提交过程，请先在发布记录中核对。")
    schedule_at = validate_schedule(schedule_at)
    draft.approval = {"version": version, "hash": bundle_hash(draft), "account_id": account_id, "account_name": account_name, "schedule_at": schedule_at, "approved_at": now()}
    draft.state, draft.updated_at = "approved", now()
    enqueue(s, "publish", {"draft_id": draft.id, **draft.approval}, dedupe=f"publish:{draft.id}:{version}")


def invalidate_approval(s, draft):
    if draft.state in ("submitting", "submitted", "unknown", "published"):
        raise ValueError("该版本已进入提交过程，请先核对平台状态；修改请创建副本。")
    pending = list(s.scalars(select(Job).where(Job.kind == "publish", Job.state.in_(["pending", "waiting", "running", "submitted", "unknown"]))))
    linked = [j for j in pending if j.payload.get("draft_id") == draft.id]
    if any(j.state in ("running", "submitted", "unknown") for j in linked):
        raise ValueError("该版本正在提交或已提交，请先核对平台状态；需要调整时请创建新稿。")
    for job in linked:
        job.state, job.error, job.finished_at = "cancelled", "稿件已修改，原审批失效。", now()
    draft.approval, draft.state = {}, "needs_review"


def approval_matches(draft, payload):
    return bool(draft and draft.state == "approved" and draft.version == payload.get("version") and bundle_hash(draft) == payload.get("hash") and draft.approval == {k: payload[k] for k in ("version", "hash", "account_id", "account_name", "schedule_at", "approved_at")})
