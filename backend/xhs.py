import asyncio
import fcntl
import re
from urllib.parse import urlparse

import httpx

from .db import DATA, Session, setting

class BrowserLock:
    """Serialize browser operations across both API and worker processes."""
    def __init__(self):
        self.local = asyncio.Lock()
        self.file = None

    async def __aenter__(self):
        await self.local.acquire()
        try:
            self.file = (DATA / "browser.lock").open("w")
            for _ in range(1500):
                try:
                    fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return self
                except BlockingIOError:
                    await asyncio.sleep(.2)
            raise ConnectorError("浏览器正处理其他任务，请稍后重试。")
        except BaseException:
            if self.file:
                self.file.close()
            self.local.release()
            raise

    async def __aexit__(self, *_):
        fcntl.flock(self.file, fcntl.LOCK_UN)
        self.file.close()
        self.local.release()


BROWSER_LOCK = BrowserLock()


class ConnectorError(Exception):
    def __init__(self, message, *, not_submitted=False):
        super().__init__(message)
        self.not_submitted = not_submitted


def response_error(response):
    """Only classify errors proven to occur before any publishing action."""
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    code = str(data.get("code", ""))
    detail = str(data.get("details") or data.get("message") or "")
    preflight = (
        "定时发布时间必须至少在1小时后", "定时发布时间不能超过14天",
        "定时发布时间格式错误", "标题长度超过限制",
        "创作者中心登录失效，请重新扫码登录",
    )
    rejected = code in ("INVALID_REQUEST", "UNAUTHORIZED", "FORBIDDEN") or response.status_code in (401, 403) or any(text in detail for text in preflight)
    # Strip credentials, links and paths rather than returning arbitrary upstream bodies.
    safe_detail = re.sub(r"(?i)(bearer\s+|(?:token|cookie|key|authorization)[=:]\s*)[^\s,;]+", r"\1[已隐藏]", detail)
    safe_detail = re.sub(r"https?://[^\s]+|/(?:Users|home|tmp)/[^\s]+", "[已隐藏]", safe_detail)[:350]
    message = f"小红书工具请求未成功（HTTP {response.status_code}）"
    if safe_detail:
        message += "：" + safe_detail
    return ConnectorError(message, not_submitted=rejected)


def connector_url():
    with Session() as s:
        cfg = setting(s, "connector", {"url": "http://127.0.0.1:18060"})
    url = cfg.get("url", "").rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConnectorError("小红书连接工具地址只能使用本机HTTP地址。")
    return url


async def request(method, path, payload=None, *, timeout=120):
    try:
        token_path = DATA / "connector/.auth-token"
        token = token_path.read_text().strip() if token_path.exists() else ""
        headers = {"Authorization": "Bearer " + token} if token else {}
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            r = await client.request(method, connector_url() + path, json=payload, headers=headers)
        data = r.json()
        if r.status_code >= 400 or data.get("success") is False:
            raise response_error(r)
        return data.get("data", data)
    except ConnectorError:
        raise
    except (httpx.HTTPError, ValueError):
        raise ConnectorError("无法连接本机小红书工具，请先启动连接服务。") from None


async def status():
    async with BROWSER_LOCK:
        return await request("GET", "/api/v1/login/status", timeout=35)


async def reset_login():
    # The upstream DELETE endpoint alone does not cancel its background QR waiter.
    # Restart our managed connector first so an old scan cannot restore old cookies.
    if urlparse(connector_url()).port != 18060:
        raise ConnectorError("切换账号需要使用工作台自带的本机登录服务（端口18060）。")
    from scripts.manage import restart_connector
    await asyncio.to_thread(restart_connector)
    await request("DELETE", "/api/v1/login/cookies", timeout=15)


async def identity():
    data = await request("GET", "/api/v1/user/me", timeout=60)
    candidates = []
    def walk(obj):
        if isinstance(obj, dict):
            uid = obj.get("userId") or obj.get("user_id") or obj.get("redId")
            name = obj.get("nickname") or obj.get("nick_name") or obj.get("nickName")
            if uid and name:
                candidates.append({"id": str(uid), "name": str(name)})
            for value in obj.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)
    walk(data)
    if not candidates:
        raise ConnectorError("未能核验当前账号的真实ID与名称，暂不允许发布。")
    return candidates[0]


def valid_note_id(value):
    if not re.fullmatch(r"[a-fA-F0-9]{24}", value):
        raise ConnectorError("笔记编号格式不正确，请从搜索结果选择笔记。")
    return value
