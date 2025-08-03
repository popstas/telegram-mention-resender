import atexit
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

TRACE_IDS_PATH = os.path.join("data", "trace_ids.json")


class TraceStore:
    """Store mapping from Telegram chat/message IDs to Langfuse trace IDs."""

    def __init__(self, path: str, flush_interval: int = 60) -> None:
        self.path = path
        self.flush_interval = flush_interval
        self.last_flush = time.monotonic()
        self.dirty = False
        self.data: dict[str, dict[str, str]] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if loaded and all(isinstance(v, str) for v in loaded.values()):
                    # backward compatibility with old format without chat ids
                    self.data["0"] = loaded  # type: ignore[assignment]
                else:
                    self.data = loaded
            except Exception:  # pragma: no cover - corrupt file
                self.data = {}

    def set(
        self, chat_id: int | str, message_id: int | str, trace_id: str | None
    ) -> None:
        if trace_id is None:
            return
        chat = self.data.setdefault(str(chat_id), {})
        chat[str(message_id)] = trace_id
        self.dirty = True
        if time.monotonic() - self.last_flush >= self.flush_interval:
            self.flush()

    def get(self, chat_id: int | str, message_id: int | str) -> str | None:
        return self.data.get(str(chat_id), {}).get(str(message_id))

    def flush(self) -> None:
        if not self.dirty:
            return
        logger.debug("Flushing trace ids to %s", self.path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)
        self.last_flush = time.monotonic()
        self.dirty = False


trace_ids = TraceStore(TRACE_IDS_PATH)
atexit.register(trace_ids.flush)
