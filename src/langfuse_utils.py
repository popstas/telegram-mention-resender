import logging
import os
from typing import Optional

# Delay import until credentials are set
Langfuse = None  # type: ignore

logger = logging.getLogger(__name__)


def init_langfuse(config: dict) -> Optional["Langfuse"]:
    """Initialize and return a Langfuse client if credentials are present."""
    public_key = config.get("langfuse_public_key")
    secret_key = config.get("langfuse_secret_key")
    base_url = config.get("langfuse_base_url")
    if not public_key or not secret_key:
        return None

    os.environ["LANGFUSE_PUBLIC_KEY"] = public_key
    os.environ["LANGFUSE_SECRET_KEY"] = secret_key
    if base_url:
        os.environ["LANGFUSE_HOST"] = base_url

    global Langfuse
    if Langfuse is None:
        try:  # pragma: no cover - optional import
            from langfuse import Langfuse as LangfuseCls

            Langfuse = LangfuseCls  # type: ignore
        except Exception:
            logger.info("Langfuse package not available")
            return None

    return Langfuse(public_key=public_key, secret_key=secret_key, host=base_url)
