import logging
from typing import Optional

try:
    from langfuse import Langfuse
except Exception:  # pragma: no cover - package optional
    Langfuse = None  # type: ignore

logger = logging.getLogger(__name__)


def init_langfuse(config: dict) -> Optional["Langfuse"]:
    """Initialize and return a Langfuse client if credentials are present."""
    if Langfuse is None:
        logger.info("Langfuse package not available")
        return None
    public_key = config.get("langfuse_public_key")
    secret_key = config.get("langfuse_secret_key")
    base_url = config.get("langfuse_base_url")
    if not public_key or not secret_key:
        return None
    return Langfuse(public_key=public_key, secret_key=secret_key, host=base_url)
