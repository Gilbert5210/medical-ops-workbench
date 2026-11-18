import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend import ai, worker, xhs
from backend.cards import bundle_hash, card_html
from backend.db import Draft, Job, Session, Source, now, set_setting
from backend.services import approve, import_sources, validate_schedule


def make_draft(s):
    row = Draft(audience_id="M01", title="病例整理先检查什么", body="教学讨论：先检查研究问题与资料条件。", cards=[{"heading": "先确认研究问题", "text": "列出主要变量与缺失情况。"}], tags=["医学科研"])
    s.add(row)
    s.flush()
    return row


def schedule():
    return (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()


def prepare_approval():
    with Session.begin() as s:
        draft = make_draft(s)
        approve(s, draft, 1, "account-a", "测试账号", schedule())
        return draft.id, s.scalar(select(Job)).id


def test_audience_library_and_no_fake_samples(client):
    items = client.get("/api/audiences").json()
    assert len(items) == 32
    assert all(all(a["prompts"][k] for k in "ABC") for a in items)
    assert client.get("/api/sources").json() == []
    assert client.get("/api/overview").json()["source_count"] == 0


def test_import_csv_dedupe_and_formula_export(client):
    content = 'text,url\n"=恶意公式\n下一行",https://example.com\n'
    assert client.post("/api/sources/import-text", json={"text":content}).json()["added"] == 1
    assert client.post("/api/sources/import-text", json={"text":content}).json()["added"] == 0
    exported = client.get("/api/sources/export").text
    assert "'=恶意公式" in exported


def test_cross_site_write_rejected(client):
    assert client.post("/api/sources/import", json={"items":[{"text":"test"}]}, headers={"Origin":"https://attacker.example"}).status_code == 403
    assert client.post("/api/sources/import", content='{}', headers={"Content-Type":"text/plain"}).status_code == 415


def test_approval_binds_version_and_change_cancels_job(client):
    draft_id, job_id = prepare_approval()
    with Session() as s:
        draft = s.get(Draft, draft_id)
        old_hash = draft.approval["hash"]
        assert old_hash == bundle_hash(draft)
    response = client.put(f"/api/drafts/{draft_id}", json={"version":1,"title":"修改后的标题","body":"新的内容","tags":[],"cards":[{"heading":"修改","text":"修改正文"}]})
    assert response.status_code == 200
    assert response.json()["state"] == "needs_review"
    assert response.json()["approval"] == {}
    with Session() as s:
        assert s.get(Job, job_id).state == "cancelled"
        assert bundle_hash(s.get(Draft, draft_id)) != old_hash


def test_stale_version_cannot_save(client):
    with Session.begin() as s:
        draft_id = make_draft(s).id
    body={"version":0,"title":"标题","body":"正文","tags":[],"cards":[{"heading":"标题","text":"正文"}]}
    assert client.put(f"/api/drafts/{draft_id}",json=body).status_code == 409


@pytest.mark.asyncio
async def test_stale_approval_never_calls_publisher(monkeypatch):
    draft_id,job_id=prepare_approval()
    with Session.begin() as s:
        s.get(Draft,draft_id).body="未经批准的变更"
    async def forbidden(*args,**kwargs):
        pytest.fail("审批不匹配时不应调用发布工具")
    monkeypatch.setattr(xhs,"request",forbidden)
    await worker.process_one()
    with Session() as s:
        assert s.get(Job,job_id).state=="failed"


@pytest.mark.asyncio
async def test_publish_timeout_is_unknown_and_not_retried(monkeypatch):
    draft_id,job_id=prepare_approval()
    calls=[]
    async def images(*a):return ["/test.png"]
    async def identity():return {"id":"account-a","name":"测试账号"}
    async def fail(*a,**k):
        calls.append(1)
        raise xhs.ConnectorError("timeout")
    monkeypatch.setattr(worker,"render_cards",images)
    monkeypatch.setattr(xhs,"identity",identity)
    monkeypatch.setattr(xhs,"request",fail)
    await worker.process_one()
    assert not await worker.process_one()
    with Session() as s:
        assert s.get(Job,job_id).state=="unknown"
        assert s.get(Draft,draft_id).state=="unknown"
    assert len(calls)==1


@pytest.mark.asyncio
async def test_account_mismatch_blocks_publishing(monkeypatch):
    _,job_id=prepare_approval()
    async def images(*a):return ["/test.png"]
    async def identity():return {"id":"account-b","name":"其他账号"}
    async def forbidden(*a,**k):pytest.fail("账号不匹配不应发布")
    monkeypatch.setattr(worker,"render_cards",images)
    monkeypatch.setattr(xhs,"identity",identity)
    monkeypatch.setattr(xhs,"request",forbidden)
    await worker.process_one()
    with Session() as s:assert s.get(Job,job_id).state=="failed"


def test_submitted_version_cannot_be_edited(client):
    draft_id,job_id=prepare_approval()
    with Session.begin() as s:
        s.get(Job,job_id).state="scheduled"
        s.get(Draft,draft_id).state="submitted"
    body={"version":1,"title":"新标题","body":"新正文","tags":[],"cards":[{"heading":"标题","text":"正文"}]}
    assert client.put(f"/api/drafts/{draft_id}",json=body).status_code==400


def test_cancelled_version_can_be_reapproved(client):
    draft_id,job_id=prepare_approval()
    assert client.post(f"/api/jobs/{job_id}/cancel",json={}).status_code==200
    with Session.begin() as s:
        draft=s.get(Draft,draft_id)
        assert draft.version==2
        approve(s,draft,2,"account-a","测试账号",schedule())
    with Session() as s:assert len(list(s.scalars(select(Job))))==2


@pytest.mark.asyncio
async def test_identity_classification_needs_verbatim_evidence(monkeypatch):
    with Session.begin() as s:
        import_sources(s,[{"text":"SPSS怎么用"}])
        source_id=s.scalar(select(Source)).id
    async def response(*args,**kwargs):return {"items":[{"id":source_id,"audience_id":"M01","evidence":"我是临床专硕","summary":"工具使用问题","task":"统计理解","intent":"主动求助","confidence":"高"}]},{}
    monkeypatch.setattr(ai,"complete",response)
    await worker.analyze({})
    with Session() as s:
        row=s.get(Source,source_id)
        assert row.analyzed and not row.audience_id and not row.evidence


def test_card_text_is_escaped():
    with Session.begin() as s:
        draft=make_draft(s)
        draft.cards=[{"heading":"<script>alert(1)</script>","text":"<img src=x>"}]
        output=card_html(draft)
        assert "<script>" not in output
        assert "&lt;script&gt;" in output


def test_config_does_not_expose_key(client):
    config=client.get("/api/settings").json()
    assert "key" not in config["model"]
    assert "key_configured" in config["model"]


def test_approval_requires_fresh_account(client):
    with Session.begin() as s:
        draft_id=make_draft(s).id
        set_setting(s,"account",{"id":"a","name":"账号","verified_at":(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()})
    body={"version":1,"account_id":"a","schedule_at":schedule(),"reviewed":True}
    assert client.post(f"/api/drafts/{draft_id}/approve",json=body).status_code==400


def test_confirmation_updates_local_record_without_publishing(client):
    draft_id,job_id=prepare_approval()
    with Session.begin() as s:
        s.get(Job,job_id).state="unknown"
        s.get(Draft,draft_id).state="unknown"
    response=client.post(f"/api/jobs/{job_id}/confirm",json={"state":"not_published","url":"","note":"已核实无预约"})
    assert response.status_code==200
    with Session() as s:
        row=s.get(Draft,draft_id)
        assert row.state=="needs_review" and row.version==2 and not row.approval


@pytest.mark.asyncio
async def test_generated_cover_is_final_title_not_internal_notes(monkeypatch):
    async def response(*args,**kwargs):
        return {"title":"先检查研究条件","body":"科研教学示例。","tags":["医学科研"],"cards":[{"heading":"检查变量","text":"先列出变量定义。"}],"checks":[]},{}
    monkeypatch.setattr(ai,"complete",response)
    result=await worker.generate({"audience_id":"M01","content_type":"A"})
    with Session() as s:
        draft=s.get(Draft,result["draft_id"])
        assert draft.cards[0]["heading"]==draft.title
        assert len(draft.cards)==2
        assert draft.state=="needs_review"


@pytest.mark.asyncio
async def test_internal_title_options_are_not_saved_as_cards(monkeypatch):
    async def response(*args,**kwargs):
        return {"title":"先检查研究条件","body":"科研教学示例。","tags":[],"cards":[{"heading":"三个标题备选","text":"不能进入发布内容。"}],"checks":[]},{}
    monkeypatch.setattr(ai,"complete",response)
    with pytest.raises(ValueError):
        await worker.generate({"audience_id":"M01","content_type":"A"})
    with Session() as s:
        assert list(s.scalars(select(Draft)))==[]


def test_daily_plan_creates_one_review_task_and_no_publish(monkeypatch):
    from zoneinfo import ZoneInfo
    fixed=datetime(2026,11,15,9,0,tzinfo=ZoneInfo("Asia/Shanghai"))
    class FixedDatetime(datetime):
        @classmethod
        def now(cls,tz=None):
            return fixed.astimezone(tz) if tz else fixed
    monkeypatch.setattr(worker,"datetime",FixedDatetime)
    with Session.begin() as s:
        set_setting(s,"daily",{"enabled":True,"time":"09:00","audience_id":"M01","content_type":"A"})
    worker.daily_tick()
    worker.daily_tick()
    with Session() as s:
        jobs=list(s.scalars(select(Job)))
        assert len(jobs)==1 and jobs[0].kind=="generate"


@pytest.mark.asyncio
async def test_connector_search_and_comment_import_dedupe(monkeypatch):
    fid="0123456789abcdef01234567"
    async def request(method,path,payload=None,**kwargs):
        if path.endswith("search"):
            return {"feeds":[{"id":fid,"xsecToken":"test-token","noteCard":{"displayTitle":"临床专硕数据整理","interactInfo":{"commentCount":"2"}}}]}
        assert payload["comment_config"]["max_comment_items"]==30
        return {"feed_id":fid,"data":{"note":{"title":"临床专硕数据整理","desc":"如何开始核对变量？"},"comments":{"list":[{"id":"c1","content":"我是临床专硕，想学习变量整理。","userInfo":{"userId":"not-needed"},"ipLocation":"not-needed"}],"hasMore":True}}}
    monkeypatch.setattr(xhs,"request",request)
    assert (await worker.collect({"keyword":"临床专硕","limit":10}))["added"]==1
    assert (await worker.collect({"keyword":"临床专硕","limit":10}))["added"]==0
    with Session() as s:
        source_id=s.scalar(select(Source)).id
    assert (await worker.collect({"source_id":source_id}))["added"]==1
    assert (await worker.collect({"source_id":source_id}))["added"]==0
    with Session() as s:
        rows=list(s.scalars(select(Source)))
        assert len(rows)==2
        assert rows[-1].kind=="comment"
        assert "userInfo" not in rows[-1].meta and "ipLocation" not in rows[-1].meta


@pytest.mark.parametrize("offset", [timedelta(minutes=5), timedelta(days=60), timedelta(days=-1)])
async def test_publish_has_no_local_time_window(offset, monkeypatch):
    chosen = (datetime.now(timezone.utc) + offset).isoformat()
    assert validate_schedule(chosen) == chosen
    with Session.begin() as s:
        draft = make_draft(s)
        approve(s, draft, 1, "account-a", "测试账号", chosen)
        draft_id = draft.id
        job_id = s.scalar(select(Job)).id
    sent = []
    async def images(*args):
        return ["/test.png"]
    async def identity():
        return {"id": "account-a", "name": "测试账号"}
    async def request(method, path, payload, **kwargs):
        sent.append(payload)
        return {"status": "发布完成"}
    monkeypatch.setattr(worker, "render_cards", images)
    monkeypatch.setattr(xhs, "identity", identity)
    monkeypatch.setattr(xhs, "request", request)
    await worker.process_one()
    waiting = offset > timedelta(0)
    assert len(sent) == (0 if waiting else 1)
    if not waiting:
        assert "schedule_at" not in sent[0]
    with Session() as s:
        assert s.get(Job, job_id).state == ("waiting" if waiting else "submitted")
        assert s.get(Draft, draft_id).state == ("approved" if waiting else "submitted")


def test_connector_preserves_preflight_error():
    import httpx
    response = httpx.Response(500, json={"success": False, "code": "PUBLISH_FAILED", "details": "定时发布时间必须至少在1小时后，当前设置无效"})
    error = xhs.response_error(response)
    assert error.not_submitted
    assert "至少在1小时后" in str(error)
    uncertain = xhs.response_error(httpx.Response(500, json={"code":"PUBLISH_FAILED", "details":"等待发布成功页面超时"}))
    assert not uncertain.not_submitted


@pytest.mark.asyncio
async def test_known_preflight_rejection_is_retryable(monkeypatch):
    draft_id, job_id = prepare_approval()
    async def images(*args):return ["/test.png"]
    async def identity():return {"id":"account-a", "name":"测试账号"}
    async def reject(*args, **kwargs):
        raise xhs.ConnectorError("定时发布时间必须至少在1小时后", not_submitted=True)
    monkeypatch.setattr(worker,"render_cards",images)
    monkeypatch.setattr(xhs,"identity",identity)
    monkeypatch.setattr(xhs,"request",reject)
    await worker.process_one()
    with Session() as s:
        assert s.get(Job,job_id).state == "rejected"
        assert s.get(Draft,draft_id).state == "rejected"
        assert "至少在1小时后" in s.get(Job,job_id).error


def test_only_known_rejection_can_be_retried(client):
    draft_id, job_id = prepare_approval()
    with Session.begin() as s:
        s.get(Job,job_id).state="unknown"
        s.get(Draft,draft_id).state="unknown"
    assert client.post(f"/api/jobs/{job_id}/retry",json={"confirmed":True,"publish_now":True}).status_code==400
    with Session.begin() as s:
        s.get(Job,job_id).state="rejected"
        s.get(Job,job_id).error="发布前参数校验失败"
        s.get(Draft,draft_id).state="rejected"
    response=client.post(f"/api/jobs/{job_id}/retry",json={"confirmed":True,"publish_now":True})
    assert response.status_code==200
    assert response.json()["state"]=="pending"
    assert response.json()["payload"]["attempt"]==2
    assert response.json()["payload"]["history"][0]["state"]=="rejected"


@pytest.mark.asyncio
async def test_local_timer_does_not_block_other_work_and_runs_when_due(monkeypatch):
    with Session.begin() as s:
        draft=make_draft(s)
        approve(s,draft,1,"account-a","测试账号",(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat())
        publish_id=s.scalar(select(Job)).id
        job=Job(kind="analyze",payload={});s.add(job);s.flush();other_id=job.id
    async def analyze(payload):return {"analyzed":1}
    monkeypatch.setitem(worker.HANDLERS,"analyze",analyze)
    await worker.process_one()
    with Session() as s:
        assert s.get(Job,publish_id).state=="waiting"
        assert s.get(Job,other_id).state=="completed"
    async def images(*args):return ["/test.png"]
    async def identity():return {"id":"account-a", "name":"测试账号"}
    sent=[]
    async def request(method,path,payload,**kwargs):sent.append(payload);return {"status":"发布完成"}
    monkeypatch.setattr(worker,"render_cards",images)
    monkeypatch.setattr(xhs,"identity",identity)
    monkeypatch.setattr(xhs,"request",request)
    monkeypatch.setattr(worker,"delivery_plan",lambda _:"immediate")
    await worker.process_one()
    assert len(sent)==1 and "schedule_at" not in sent[0]
    assert not await worker.process_one()


def test_waiting_task_can_be_cancelled(client):
    draft_id,job_id=prepare_approval()
    with Session.begin() as s:s.get(Job,job_id).state="waiting"
    assert client.post(f"/api/jobs/{job_id}/cancel",json={}).status_code==200
    with Session() as s:
        assert s.get(Job,job_id).state=="cancelled"
        assert not s.get(Draft,draft_id).approval


def test_switch_account_revokes_queue_and_keeps_uncertain_results(client, monkeypatch):
    draft_id, job_id = prepare_approval()
    with Session.begin() as s:
        set_setting(s, "account", {"id": "account-a", "name": "旧账号"})
        uncertain = make_draft(s)
        uncertain.state = "unknown"
        uncertain_id = uncertain.id
        s.add(Job(kind="publish", state="unknown", payload={"draft_id": uncertain.id}, error="请核对"))
    calls = []
    async def reset():calls.append(True)
    monkeypatch.setattr(xhs, "reset_login", reset)
    response = client.post("/api/connector/logout", json={})
    assert response.status_code == 200 and response.json()["cancelled"] == 1
    assert calls == [True]
    assert client.get("/api/settings").json()["account"] == {}
    with Session() as s:
        draft = s.get(Draft, draft_id)
        assert draft.state == "needs_review" and not draft.approval and draft.version == 2
        assert s.get(Job, job_id).state == "cancelled"
        assert s.get(Draft, uncertain_id).state == "unknown"
        assert s.scalar(select(Job).where(Job.state == "unknown")).error == "请核对"
    assert client.post(f"/api/jobs/{job_id}/retry", json={"confirmed":True}).status_code == 400


def test_switch_cannot_interrupt_active_publish(client, monkeypatch):
    _, job_id = prepare_approval()
    with Session.begin() as s:s.get(Job, job_id).state = "running"
    async def forbidden():pytest.fail("发布中不应退出登录")
    monkeypatch.setattr(xhs, "reset_login", forbidden)
    response = client.post("/api/connector/logout", json={})
    assert response.status_code == 400 and "正在执行" in response.json()["detail"]


def test_failed_reset_leaves_publishing_disabled(client, monkeypatch):
    _, job_id = prepare_approval()
    async def fail():raise xhs.ConnectorError("登录服务暂不可用")
    monkeypatch.setattr(xhs, "reset_login", fail)
    assert client.post("/api/connector/logout", json={}).status_code == 400
    assert client.get("/api/settings").json()["account"] == {}
    with Session() as s:assert s.get(Job, job_id).state == "cancelled"


def test_creator_login_failure_occurs_before_submission():
    import httpx
    error = xhs.response_error(httpx.Response(500, json={"code":"PUBLISH_FAILED", "details":"创作者中心登录失效，请重新扫码登录"}))
    assert error.not_submitted


def test_publish_connection_check_never_publishes(client, monkeypatch):
    calls = []
    async def identity():return {"id":"account-a", "name":"测试账号"}
    async def request(method, path, **kwargs):
        calls.append((method, path))
        return {"is_logged_in": True}
    monkeypatch.setattr(xhs, "identity", identity)
    monkeypatch.setattr(xhs, "request", request)
    response = client.post("/api/connector/check-publish", json={})
    assert response.status_code == 200 and response.json()["is_logged_in"]
    assert response.json()["account"]["id"] == "account-a"
    assert calls == [("GET", "/api/v1/login/creator-status")]


def test_stopped_connector_zombie_does_not_block_restart(monkeypatch):
    from scripts import manage
    from types import SimpleNamespace
    monkeypatch.setattr(manage.os, 'kill', lambda *_: None)
    monkeypatch.setattr(manage.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout='Z  '))
    assert not manage.running(1234)
