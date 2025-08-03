import json
from pathlib import Path

from src.trace_ids import TraceStore


def test_trace_store(tmp_path):
    path = tmp_path / "trace_ids.json"
    store = TraceStore(str(path), flush_interval=0)
    store.set(1, 123, "abc")
    assert json.loads(path.read_text(encoding="utf-8")) == {"1": {"123": "abc"}}
    new_store = TraceStore(str(path))
    assert new_store.get(1, 123) == "abc"
