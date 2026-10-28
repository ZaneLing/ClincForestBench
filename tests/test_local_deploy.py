"""Safety regressions for the local background deploy entry point."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import socket
import time

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/dev/local_deploy.py"
spec = importlib.util.spec_from_file_location("local_deploy", MODULE_PATH)
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def test_pid_reuse_is_not_owned(monkeypatch):
    owner = {"pid": 123, "started": "old", "command": "bash start_app.sh"}
    monkeypatch.setattr(deploy, "fingerprint", lambda _: dict(owner, started="new"))
    assert not deploy.alive(owner)


def test_port_range_is_validated():
    assert deploy.positive("3000") == 3000
    for value in ("0", "65536", "-1"):
        with pytest.raises(deploy.argparse.ArgumentTypeError):
            deploy.positive(value)


def test_foreign_state_is_rejected(tmp_path):
    state = tmp_path / "deployment.json"
    state.write_text('{"root": "/other-project"}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="不属于当前项目"):
        deploy.read_state(state)


def test_reused_process_is_never_signalled(monkeypatch, tmp_path):
    monkeypatch.setattr(deploy, "read_state", lambda _: {
        "root": str(deploy.ROOT), "managed": False, "owner": {"pid": 123}})
    monkeypatch.setattr(deploy, "alive", lambda _: True)
    monkeypatch.setattr(deploy.os, "kill", lambda *_: pytest.fail("must not kill reused service"))
    with pytest.raises(RuntimeError, match="不会擅自停止"):
        deploy.stop(tmp_path / "deployment.json")


def test_foreign_port_is_not_killed_or_replaced(monkeypatch, tmp_path):
    monkeypatch.setattr(deploy, "read_state", lambda _: None)
    monkeypatch.setattr(deploy, "inspect_existing", lambda *_: None)
    monkeypatch.setattr(deploy, "is_open", lambda _: True)
    monkeypatch.setattr(deploy.subprocess, "Popen", lambda *_a, **_k: pytest.fail("must not launch"))
    args = SimpleNamespace(api_port=8000, web_port=3000, timeout=10, no_install=True)
    with pytest.raises(RuntimeError, match="不会抢占或停止"):
        deploy.start(args, tmp_path / "deployment.json", tmp_path)


def test_existing_project_is_adopted_without_restart(monkeypatch, tmp_path):
    owner = {"pid": 123, "started": "today", "command": "bash start_app.sh"}
    monkeypatch.setattr(deploy, "read_state", lambda _: None)
    monkeypatch.setattr(deploy, "inspect_existing", lambda *_: owner)
    monkeypatch.setattr(deploy, "health", lambda *_: {"status": "ok", "case_count": 130})
    monkeypatch.setattr(deploy.subprocess, "Popen", lambda *_a, **_k: pytest.fail("must not launch"))
    args = SimpleNamespace(api_port=8000, web_port=3000, timeout=10, no_install=True)
    path = tmp_path / "deployment.json"
    deploy.start(args, path, tmp_path)
    saved = deploy.json.loads(path.read_text(encoding="utf-8"))
    assert saved["managed"] is False
    assert saved["owner"] == owner


def test_wrong_process_group_is_never_signalled(monkeypatch):
    monkeypatch.setattr(deploy, "alive", lambda _: True)
    monkeypatch.setattr(deploy.os, "getpgid", lambda _: 999)
    monkeypatch.setattr(deploy.os, "kill", lambda *_: pytest.fail("must not signal foreign process group"))
    with pytest.raises(RuntimeError, match="进程组不匹配"):
        deploy.terminate_owned({"managed": True, "owner": {"pid": 123}})


def test_parallel_vinext_instance_is_rejected_before_launch(monkeypatch, tmp_path):
    monkeypatch.setattr(deploy, "read_state", lambda _: None)
    monkeypatch.setattr(deploy, "inspect_existing", lambda *_: None)
    monkeypatch.setattr(deploy, "is_open", lambda _: False)
    monkeypatch.setattr(deploy, "active_project_web_server", lambda: 123)
    monkeypatch.setattr(deploy.subprocess, "Popen", lambda *_a, **_k: pytest.fail("must not launch"))
    args = SimpleNamespace(api_port=8100, web_port=3100, timeout=10, no_install=True)
    with pytest.raises(RuntimeError, match="不支持双开"):
        deploy.start(args, tmp_path / "deployment.json", tmp_path)


def test_managed_background_start_idempotence_and_stop(monkeypatch, tmp_path):
    """Run real detached processes in a fixture, never touch the real app/database."""
    root = tmp_path / "fixture project"
    script_dir = root / "scripts/dev"
    script_dir.mkdir(parents=True)
    fixture = script_dir / "start_app.sh"
    fixture.write_text('''#!/usr/bin/env bash
set -euo pipefail
api=""; web=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-port) api="$2"; shift 2 ;;
    --web-port) web="$2"; shift 2 ;;
    --host|--timeout) shift 2 ;;
    *) shift ;;
  esac
done
cleanup() {
  kill "$api_pid" "$web_pid" 2>/dev/null || true
  wait "$api_pid" "$web_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' TERM INT
"$FIXTURE_PYTHON" server.py "$api" api &
api_pid=$!
"$FIXTURE_PYTHON" server.py "$web" web &
web_pid=$!
wait
''', encoding="utf-8")
    (root / "server.py").write_text('''import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = b'{"status":"ok","case_count":0,"temporal_case_count":0}' if sys.argv[2] == "api" else b"fixture"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, *args):
        pass
HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
''', encoding="utf-8")
    monkeypatch.setattr(deploy, "ROOT", root)
    monkeypatch.setattr(deploy, "active_project_web_server", lambda: None)
    monkeypatch.setattr(deploy, "inspect_existing", lambda *_: None)
    monkeypatch.setenv("FIXTURE_PYTHON", deploy.sys.executable)
    sockets = [socket.socket(), socket.socket()]
    for sock in sockets:
        sock.bind(("127.0.0.1", 0))
    api_port, web_port = [sock.getsockname()[1] for sock in sockets]
    for sock in sockets:
        sock.close()
    run_dir = root / ".run"
    run_dir.mkdir()
    path = run_dir / "deployment.json"
    args = SimpleNamespace(api_port=api_port, web_port=web_port, timeout=10, no_install=True)
    try:
        deploy.start(args, path, run_dir)
        state = deploy.read_state(path)
        assert state["managed"] and deploy.alive(state["owner"])
        assert deploy.health(api_port, web_port)
        deploy.start(args, path, run_dir)
        assert deploy.read_state(path)["owner"] == state["owner"]
        deploy.stop(path)
        for _ in range(30):
            if not deploy.is_open(api_port) and not deploy.is_open(web_port):
                break
            time.sleep(0.1)
        assert not deploy.is_open(api_port)
        assert not deploy.is_open(web_port)
    finally:
        state = deploy.read_state(path)
        if state and deploy.alive(state["owner"]):
            deploy.terminate_owned(state)
