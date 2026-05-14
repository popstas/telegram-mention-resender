"""Smoke tests for scripts/test_webhook_server.py."""

import importlib.util
import json
import threading
import urllib.request
from io import StringIO
from pathlib import Path

import pytest


def _load_server_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "test_webhook_server.py"
    spec = importlib.util.spec_from_file_location("test_webhook_server", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def running_server(monkeypatch):
    module = _load_server_module()
    captured = StringIO()
    # Redirect the handler's stdout prints into our buffer.
    monkeypatch.setattr(
        "builtins.print",
        lambda *a, **k: captured.write(" ".join(str(x) for x in a) + "\n"),
    )
    # Bind to port 0 so the OS picks a free port and parallel tests don't collide.
    server = module.build_server(host="127.0.0.1", port=0)
    host, port = server.server_address[:2]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, host, port, captured
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _post(url: str, data: bytes, content_type: str) -> tuple[int, bytes]:
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": content_type}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, resp.read()


def test_server_accepts_text_payload(running_server):
    _server, host, port, captured = running_server
    body = "From: @alice, Name: Alice Doe, Message: Hello".encode("utf-8")
    status, response = _post(
        f"http://{host}:{port}/hook", body, "text/plain; charset=utf-8"
    )
    assert status == 200
    assert json.loads(response.decode("utf-8")) == {"ok": True}
    assert "Hello" in captured.getvalue()


def test_server_accepts_json_payload(running_server):
    _server, host, port, captured = running_server
    payload = {"from_username": "alice", "message_text": "Hi"}
    body = json.dumps(payload).encode("utf-8")
    status, response = _post(f"http://{host}:{port}/hook", body, "application/json")
    assert status == 200
    assert json.loads(response.decode("utf-8")) == {"ok": True}
    log = captured.getvalue()
    assert "from_username" in log
    assert "alice" in log
