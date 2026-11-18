#!/usr/bin/env python3
"""Start and stop this local workbench without touching unrelated processes."""
import json
import os
import signal
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
os.chmod(DATA, 0o700)
PYTHON = str(ROOT / ".venv/bin/python")
REGISTRY = DATA / "processes.json"
URL = "http://127.0.0.1:18765"


def running(pid):
    try:
        os.kill(pid, 0)
        # A connector launched by the API may remain a zombie until its parent
        # reaps it. It owns no port and must not block service recovery.
        state = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True).stdout.strip()
        return bool(state) and not state.startswith("Z")
    except (OSError, TypeError):
        return False


def records():
    try:
        return json.loads(REGISTRY.read_text())
    except (OSError, ValueError):
        return {}


def spawn(name, command, cwd, env=None):
    with (DATA / (name + ".log")).open("a") as log:
        process = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=log, start_new_session=True, env=env)
    return process.pid


def port_free(port):
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def start():
    state = records()
    commands = {
        "api": ([PYTHON, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "18765", "--no-access-log"], ROOT),
        "worker": ([PYTHON, "-m", "backend.worker"], ROOT),
    }
    binary = DATA / "connector/xiaohongshu-mcp"
    if binary.exists():
        commands["connector"] = ([str(binary), "-port", "127.0.0.1:18060", "-headless=true"], binary.parent)
    for name, (command, cwd) in commands.items():
        if running(state.get(name)):
            continue
        port = 18765 if name == "api" else 18060 if name == "connector" else None
        if port and not port_free(port):
            print(f"{name}对应端口已被占用，没有启动第二个进程。")
            continue
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if name == "connector":
            token_file = DATA / "connector/.auth-token"
            if not token_file.exists():
                token_file.write_text(secrets.token_urlsafe(32))
                os.chmod(token_file, 0o600)
            env["AUTH_TOKEN"] = token_file.read_text().strip()
            env["COOKIES_PATH"] = str(DATA / "connector/cookies.json")
        state[name] = spawn(name, command, cwd, env)
    REGISTRY.write_text(json.dumps(state))
    for _ in range(30):
        try:
            with urllib.request.urlopen(URL + "/api/health", timeout=1) as r:
                if r.status == 200:
                    print("工作台已启动：" + URL)
                    return
        except OSError:
            time.sleep(.3)
    raise SystemExit("工作台没有正常启动，请检查 data/api.log。")


def restart_connector():
    """Stop pending QR watchers before resetting login; leave API and worker alone."""
    state = records()
    pid = state.get("connector")
    binary = DATA / "connector/xiaohongshu-mcp"
    if not pid or not running(pid) or not binary.exists():
        raise ValueError("本机登录服务尚未启动，请先重新启动工作台。")
    command = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
    if str(binary) not in command:
        raise ValueError("无法确认登录服务归属，没有退出当前账号。请重新启动工作台。")
    os.kill(pid, signal.SIGTERM)
    for _ in range(100):
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
        if not running(pid) and port_free(18060):
            break
        time.sleep(.1)
    else:
        raise ValueError("登录服务尚未退出，请稍后重试。")
    env = os.environ.copy()
    env["AUTH_TOKEN"] = (DATA / "connector/.auth-token").read_text().strip()
    env["COOKIES_PATH"] = str(DATA / "connector/cookies.json")
    state["connector"] = spawn("connector", [str(binary), "-port", "127.0.0.1:18060", "-headless=true"], binary.parent, env)
    REGISTRY.write_text(json.dumps(state))
    for _ in range(50):
        try:
            with urllib.request.urlopen("http://127.0.0.1:18060/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(.1)
    raise ValueError("登录服务未能恢复，请重新启动工作台。")


def stop():
    stopped = []
    for name, pid in records().items():
        if not running(pid):
            continue
        # Verify PID ownership before signalling a potentially reused PID.
        command = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
        expected = {"api": "uvicorn backend.main:app", "worker": "backend.worker", "connector": "xiaohongshu-mcp"}[name]
        if expected in command:
            try:
                os.kill(pid, signal.SIGTERM)
                stopped.append(pid)
            except ProcessLookupError:
                pass
    for _ in range(30):
        if not any(running(pid) for pid in stopped):
            break
        time.sleep(.1)
    REGISTRY.unlink(missing_ok=True)
    print("工作台进程已停止。已提交到平台的预约不会被取消。")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "start"
    if action == "start":
        start()
    elif action == "stop":
        stop()
    elif action == "status":
        for name, pid in records().items():
            print(name, "运行中" if running(pid) else "已停止")
    else:
        raise SystemExit("使用 start、stop 或 status。")
