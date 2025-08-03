import atexit
import datetime
import json
import logging
import os
import time
from dataclasses import asdict, dataclass

logger = logging.getLogger(__name__)

STATS_PATH = os.path.join("data", "stats.json")


def current_day() -> str:
    """Return the current day string in UTC."""
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")


@dataclass
class Stats:
    """Statistics counters for processed messages."""

    total: int = 0
    forwarded_total: int = 0
    forwarded_words: int = 0
    forwarded_prompt: int = 0
    tokens: int = 0

    @classmethod
    def from_dict(cls, data: dict | None) -> "Stats":
        data = data or {}
        return cls(
            total=data.get("total", 0),
            forwarded_total=data.get("forwarded_total", 0),
            forwarded_words=data.get("forwarded_words", 0),
            forwarded_prompt=data.get("forwarded_prompt", 0),
            tokens=data.get("tokens", 0),
        )

    def to_dict(self) -> dict:
        return asdict(self)


def convert(data: dict) -> dict:
    """Convert stats from the old format to the new one."""

    if "stats" in data:
        return data

    new_data = {
        "stats": Stats(
            total=data.get("total", 0), tokens=data.get("tokens", 0)
        ).to_dict(),
        "instances": [],
    }

    for inst in data.get("instances", []):
        inst_data = {
            "name": inst.get("name"),
            "stats": Stats(
                total=inst.get("total", 0), tokens=inst.get("tokens", 0)
            ).to_dict(),
            "days": {},
            "tokens": inst.get("tokens", 0),
        }
        for day, val in inst.get("days", {}).items():
            if isinstance(val, dict) and "stats" in val:
                inst_data["days"][day] = val
            else:
                inst_data["days"][day] = {"stats": Stats(total=val).to_dict()}
        new_data["instances"].append(inst_data)

    return new_data


class StatsTracker:
    """Collect and periodically flush statistics about processed messages."""

    def __init__(self, path: str, flush_interval: int = 60) -> None:
        self.path = path
        self.flush_interval = flush_interval
        self.last_flush = time.monotonic()
        self.dirty = False
        self.data = {"stats": Stats().to_dict(), "instances": []}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                if "stats" not in self.data:
                    self.data = convert(self.data)
            except Exception:  # pragma: no cover - corrupt file
                self.data = {"stats": Stats().to_dict(), "instances": []}

    def _get_inst(self, name: str) -> dict:
        for inst in self.data.get("instances", []):
            if inst.get("name") == name:
                inst.setdefault("stats", Stats().to_dict())
                inst.setdefault("tokens", 0)
                return inst
        inst = {"name": name, "stats": Stats().to_dict(), "days": {}, "tokens": 0}
        self.data.setdefault("instances", []).append(inst)
        return inst

    def increment(
        self,
        name: str,
        forwarded: bool = False,
        used_word: bool = False,
        used_prompt: bool = False,
    ) -> None:
        inst = self._get_inst(name)
        day = current_day()
        day_stat = inst["days"].setdefault(day, {"stats": Stats().to_dict()})
        for scope in (self.data["stats"], inst["stats"], day_stat["stats"]):
            scope["total"] = scope.get("total", 0) + 1
            if forwarded:
                scope["forwarded_total"] = scope.get("forwarded_total", 0) + 1
                if used_word:
                    scope["forwarded_words"] = scope.get("forwarded_words", 0) + 1
                if used_prompt:
                    scope["forwarded_prompt"] = scope.get("forwarded_prompt", 0) + 1
        self.dirty = True
        if time.monotonic() - self.last_flush >= self.flush_interval:
            self.flush()

    def add_tokens(self, name: str, tokens: int) -> None:
        if tokens <= 0:
            return
        inst = self._get_inst(name)
        self.data["stats"]["tokens"] = self.data["stats"].get("tokens", 0) + tokens
        inst["stats"]["tokens"] = inst["stats"].get("tokens", 0) + tokens
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
