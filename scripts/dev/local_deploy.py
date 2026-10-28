#!/usr/bin/env python3
"""Project-local background launcher; never kill a process by port number."""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def run_output(args):
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def fingerprint(pid):
    """Start time prevents PID-reuse from targeting a different process."""
    started = run_output(["ps", "-p", str(pid), "-o", "lstart="])
    command = run_output(["ps", "-ww", "-p", str(pid), "-o", "command="])
    if not started or not command:
        return None
    return {"pid": pid, "started": started, "command": command}


def process_cwd(pid):
    output = run_output(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"])
    return next((line[1:] for line in output.splitlines() if line.startswith("n")), "")


def alive(owner):
    return bool(owner and fingerprint(owner["pid"]) == owner)


def listener_pids(port):
    output = run_output(["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN", "-t"])
    return sorted({int(line) for line in output.splitlines() if line.isdigit()})


def parent_pid(pid):
    value = run_output(["ps", "-p", str(pid), "-o", "ppid="])
    return int(value) if value.isdigit() else 0


def supervisor_for(pid):
    seen = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        owner = fingerprint(pid)
        if owner and str(ROOT / "scripts/dev/start_app.sh") in owner["command"]:
            if process_cwd(pid) == str(ROOT):
                return owner
        pid = parent_pid(pid)
    return None


def belongs_to_project(pid, service):
    owner = fingerprint(pid)
    if not owner:
        return False
    cwd = process_cwd(pid)
    if service == "api":
        return cwd == str(ROOT) and bool(supervisor_for(pid))
    return cwd == str(ROOT / "frontend") and "vinext" in owner["command"]


def health(api_port, web_port):
    # Do not send local requests through proxy settings.
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with client.open("http://127.0.0.1:%d/health" % api_port, timeout=3) as response:
            payload = json.load(response)
        if payload.get("status") != "ok" or not isinstance(payload.get("case_count"), int):
            return None
        with client.open("http://127.0.0.1:%d/" % web_port, timeout=5) as response:
            if response.status != 200:
                return None
        return payload
    except (OSError, ValueError, urllib.error.URLError):
        return None


def is_open(port):
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def inspect_existing(api_port, web_port):
    api_pids, web_pids = listener_pids(api_port), listener_pids(web_port)
    if not api_pids or not web_pids:
        return None
    if not all(belongs_to_project(pid, "api") for pid in api_pids):
        return None
    if not all(belongs_to_project(pid, "web") for pid in web_pids):
        return None
    owners = [supervisor_for(pid) for pid in api_pids + web_pids]
    if not all(owners) or len({owner["pid"] for owner in owners}) != 1:
        return None
    return owners[0]


def active_project_web_server():
    """Vinext allows only one dev instance per project, even on other ports."""
    processes = run_output(["ps", "-ax", "-ww", "-o", "pid=,command="])
    entry = str(ROOT / "frontend/node_modules/.bin/vinext")
    for line in processes.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit() and entry in parts[1] and " dev" in parts[1]:
            pid = int(parts[0])
            if process_cwd(pid) == str(ROOT / "frontend"):
                return pid
    return None


def save_state(path, state):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def read_state(path):
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("root") != str(ROOT):
        raise RuntimeError("状态文件不属于当前项目；未执行任何进程操作。")
    return state


@contextlib.contextmanager
def deployment_lock(run_dir):
    with (run_dir / "deploy.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("另一个部署操作正在进行，请稍后重试。")
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def print_status(state, payload):
    api_port, web_port = state["api_port"], state["web_port"]
    print("MedTreeBench 已就绪（仅本机可访问）")
    print("应用：http://127.0.0.1:%d/" % web_port)
    print("API：http://127.0.0.1:%d/docs" % api_port)
    if payload:
        print("已加载病例：%d" % payload["case_count"])
    print("日志目录：%s" % state["log_dir"])
    if not state.get("managed"):
        print("复用已运行服务；不会重复启动或停止原终端中的服务。")
    else:
        print("服务在后台运行；关闭当前终端不会停止。")


def recent_log(path):
    if path.exists():
        with path.open(encoding="utf-8", errors="replace") as handle:
            return "".join(handle.readlines()[-30:])
    return ""


def terminate_owned(state):
    owner = state.get("owner")
    if not state.get("managed") or not alive(owner):
        return False
    # Managed launches use a dedicated session. Never signal another session.
    if os.getpgid(owner["pid"]) != owner["pid"]:
        raise RuntimeError("进程组不匹配，拒绝停止。")
    os.kill(owner["pid"], signal.SIGTERM)
    for _ in range(100):
        if not alive(owner):
            return True
        time.sleep(0.1)
    raise RuntimeError("服务未及时停止；请检查日志。未强制杀死其它进程。")


def reset_child_signals():
    # The calling host may ignore or block TERM/INT. Reset both dispositions
    # and the mask before exec; this launcher is a single-threaded CLI.
    signal.pthread_sigmask(signal.SIG_SETMASK, [])
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGHUP, signal.SIG_DFL)


def start(args, state_path, run_dir):
    previous = read_state(state_path)
    if previous and alive(previous.get("owner")):
        payload = health(args.api_port, args.web_port)
        if payload:
            print_status(previous, payload)
            return
        raise RuntimeError("已有部署进程仍在运行但健康检查失败；请检查日志后执行 stop。")

    existing = inspect_existing(args.api_port, args.web_port)
    if existing:
        payload = health(args.api_port, args.web_port)
        if not payload:
            raise RuntimeError("现有项目服务健康检查失败；未重复启动。")
        state = {"root": str(ROOT), "managed": False, "owner": existing,
                 "api_port": args.api_port, "web_port": args.web_port,
                 "log_dir": str(ROOT / ".run")}
        save_state(state_path, state)
        print_status(state, payload)
        return

    if is_open(args.api_port) or is_open(args.web_port):
        raise RuntimeError("端口已被其它服务或不完整服务占用；不会抢占或停止。"
                           "可用 --api-port / --web-port 选择空闲端口。")
    if active_project_web_server():
        raise RuntimeError("同一项目已有 Vinext 前端实例在其它端口运行；不支持双开。"
                           "请复用现有端口，或在原终端停止后再部署。")

    log_dir = run_dir / ("deploy-%d-%d-%s-%d" % (
        args.api_port, args.web_port, time.strftime("%Y%m%d-%H%M%S"), os.getpid()))
    log_dir.mkdir(mode=0o700)
    launcher_log = log_dir / "launcher.log"
    command = ["bash", str(ROOT / "scripts/dev/start_app.sh"),
               "--host", "127.0.0.1", "--api-port", str(args.api_port),
               "--web-port", str(args.web_port), "--no-open", "--timeout", str(args.timeout)]
    if args.no_install:
        command.append("--no-install")
    environment = os.environ.copy()
    environment["CFB_RUN_DIR"] = str(log_dir)
    # Background mode must not tail logs or open GUI from a shell script.
    environment["CFB_TAIL_LOGS"] = "0"
    with launcher_log.open("ab") as output:
        process = subprocess.Popen(command, cwd=str(ROOT), env=environment,
                                   stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                   start_new_session=True, preexec_fn=reset_child_signals)
    owner = fingerprint(process.pid)
    if not owner:
        raise RuntimeError("启动进程提前退出：\n" + recent_log(launcher_log))
    state = {"root": str(ROOT), "managed": True, "owner": owner,
             "api_port": args.api_port, "web_port": args.web_port, "log_dir": str(log_dir)}
    save_state(state_path, state)
    try:
        deadline = time.monotonic() + args.timeout + 30
        while time.monotonic() < deadline:
            if not alive(owner):
                raise RuntimeError("启动失败：\n" + recent_log(launcher_log))
            payload = health(args.api_port, args.web_port)
            if payload:
                print_status(state, payload)
                return
            time.sleep(1)
        raise RuntimeError("启动超时：\n" + recent_log(launcher_log))
    except BaseException:
        terminate_owned(state)
        raise


def stop(state_path):
    state = read_state(state_path)
    if not state or not alive(state.get("owner")):
        print("该部署入口没有正在运行的后台服务。")
        return
    if not state.get("managed"):
        raise RuntimeError("当前复用的是原终端启动的服务，不会擅自停止。"
                           "请在原终端按 Ctrl-C；之后 deploy.command 会以后台方式启动。")
    terminate_owned(state)
    print("本部署入口启动的前后端已停止，数据库与病例文件保留。")


def positive(value):
    number = int(value)
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("必须在 1–65535 之间")
    return number


def main():
    parser = argparse.ArgumentParser(description="MedTreeBench 一键本地后台部署（只绑定 127.0.0.1）")
    parser.add_argument("action", choices=["start", "status", "stop"], nargs="?", default="start")
    parser.add_argument("--api-port", type=positive, default=8000)
    parser.add_argument("--web-port", type=positive, default=3000)
    parser.add_argument("--timeout", type=positive, default=180)
    parser.add_argument("--no-install", action="store_true", help="依赖缺失时直接报错，不安装")
    args = parser.parse_args()
    if args.api_port == args.web_port:
        parser.error("前后端端口不能相同")
    run_dir = ROOT / ".run"
    run_dir.mkdir(exist_ok=True)
    state_path = run_dir / ("deployment-%d-%d.json" % (args.api_port, args.web_port))
    try:
        with deployment_lock(run_dir):
            if args.action == "start":
                start(args, state_path, run_dir)
            elif args.action == "stop":
                stop(state_path)
            else:
                state = read_state(state_path)
                if not state or not alive(state.get("owner")):
                    raise RuntimeError("没有该部署入口记录的在线服务；运行 ./deploy.command start。")
                payload = health(args.api_port, args.web_port)
                if not payload:
                    raise RuntimeError("服务进程存在，但健康检查未通过。")
                print_status(state, payload)
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        print("部署未完成：%s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
