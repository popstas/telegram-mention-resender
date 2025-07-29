import atexit
import datetime
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

STATS_PATH = os.path.join("data", "stats.json")


class StatsTracker:
    """Collect and periodically flush statistics about processed messages."""

    def __init__(self, path: str, flush_interval: int = 60) -> None:
        self.path = path
        self.flush_interval = flush_interval
        self.last_flush = time.monotonic()
        self.dirty = False
        self.data = {"total": 0, "tokens": 0, "instances": []}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:  # pragma: no cover - corrupt file
                self.data = {"total": 0, "tokens": 0, "instances": []}
        self.data.setdefault("tokens", 0)

    def _get_inst(self, name: str) -> dict:
        for inst in self.data.get("instances", []):
            if inst.get("name") == name:
                inst.setdefault("tokens", 0)
                return inst
        inst = {"name": name, "total": 0, "tokens": 0, "days": {}}
        self.data.setdefault("instances", []).append(inst)
        return inst

    def increment(self, name: str) -> None:
        inst = self._get_inst(name)
        self.data["total"] = self.data.get("total", 0) + 1
        inst["total"] = inst.get("total", 0) + 1
        day = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
        inst["days"][day] = inst["days"].get(day, 0) + 1
        self.dirty = True
        if time.monotonic() - self.last_flush >= self.flush_interval:
            self.flush()

    def add_tokens(self, name: str, tokens: int) -> None:
        if tokens <= 0:
            return
        inst = self._get_inst(name)
        self.data["tokens"] = self.data.get("tokens", 0) + tokens
        inst["tokens"] = inst.get("tokens", 0) + tokens
        self.dirty = True
        if time.monotonic() - self.last_flush >= self.flush_interval:
            self.flush()

    def flush(self) -> None:
        if not self.dirty:
            return
        logger.debug("Flushing stats to %s", self.path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)
        self.last_flush = time.monotonic()
        self.dirty = False


stats = StatsTracker(STATS_PATH)
atexit.register(stats.flush)
