import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Boolean, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("WORKBENCH_DATA", ROOT / "data"))
DATA.mkdir(parents=True, exist_ok=True)
os.chmod(DATA, 0o700)
engine = create_engine(f"sqlite:///{DATA / 'workbench.sqlite3'}", connect_args={"check_same_thread": False, "timeout": 30})


@event.listens_for(engine, "connect")
def configure_sqlite(connection, _):
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")


Session = sessionmaker(engine, expire_on_commit=False)


def now():
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Audience(Base):
    __tablename__ = "audiences"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    need: Mapped[str] = mapped_column(Text)
    boundary: Mapped[str] = mapped_column(Text)
    topics: Mapped[dict] = mapped_column(JSON)
    prompts: Mapped[dict] = mapped_column(JSON, default=dict)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str] = mapped_column(String, default="manual")
    title: Mapped[str] = mapped_column(String, default="")
    text: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String, default="")
    keyword: Mapped[str] = mapped_column(String, default="")
    audience_id: Mapped[str] = mapped_column(String, default="")
    task: Mapped[str] = mapped_column(String, default="待判断")
    intent: Mapped[str] = mapped_column(String, default="未知")
    summary: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String, default="待分析")
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=now)


class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    audience_id: Mapped[str] = mapped_column(String, default="")
    content_type: Mapped[str] = mapped_column(String, default="A")
    platform: Mapped[str] = mapped_column(String, default="小红书")
    title: Mapped[str] = mapped_column(String, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    cards: Mapped[list] = mapped_column(JSON, default=list)
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    checks: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String, default="needs_review")
    approval: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, default="pending")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    dedupe: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=now)
    started_at: Mapped[str] = mapped_column(String, default="")
    finished_at: Mapped[str] = mapped_column(String, default="")


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String)
    metrics: Mapped[dict] = mapped_column(JSON)
    analysis: Mapped[dict] = mapped_column(JSON)
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String, default=now)


def setting(s, key, default=None):
    row = s.get(Setting, key)
    return row.value if row else (default or {})


def set_setting(s, key, value):
    row = s.get(Setting, key)
    if row:
        row.value = value
    else:
        s.add(Setting(key=key, value=value))


def initialize():
    import json
    import re
    Base.metadata.create_all(engine)
    index = ROOT / "resources" / "人群索引_v1.json"
    library = ROOT / "resources" / "医学生人群与内容提示词库_v1.md"
    text = library.read_text() if library.exists() else ""
    if index.exists():
        with Session.begin() as s:
            for item in json.loads(index.read_text()):
                if s.get(Audience, item["id"]):
                    continue
                prompts = {}
                for typ in "ABC":
                    match = re.search(r"\*\*" + item["id"] + "-" + typ + r"｜[^\n]+\*\*\s+```text\n(.*?)\n```", text, re.S)
                    prompts[typ] = match.group(1) if match else ""
                s.add(Audience(id=item["id"], name=item["audience"], need=item["need_hypothesis"], boundary=item["boundary"], topics=item["topics"], prompts=prompts))
