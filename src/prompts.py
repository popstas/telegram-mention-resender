import asyncio
import logging
from dataclasses import dataclass

import httpx
from openai import OpenAI
from pydantic import BaseModel

from .stats import StatsTracker

logger = logging.getLogger(__name__)

config: dict = {}
stats: StatsTracker | None = None


@dataclass
class Prompt:
    """Prompt description for LLM evaluation."""

    name: str | None = None
    prompt: str | None = None
    threshold: int = 4


class EvaluateResult(BaseModel):
    """Result returned by LLM evaluation."""

    similarity: int
    main_fragment: str = ""


async def match_prompt(
    prompt: Prompt, text: str, inst_name: str | None = None
) -> EvaluateResult:
    """Return :class:`EvaluateResult` for ``text`` using OpenAI."""
    if not prompt.prompt or not config.get("openai_api_key"):
        return EvaluateResult(similarity=0, main_fragment="")

    proxy = config.get("proxy_url")
    http_client = httpx.Client(proxy=proxy) if proxy else None
    client = OpenAI(api_key=config["openai_api_key"], http_client=http_client)
    model = config.get("openai_model", "gpt-4.1-mini")

    messages = [
        {
            "role": "system",
            "content": (
                f"{prompt.prompt}\n\n"
                "Evaluate message similarity: 0 - not match at all, 5 - strongly match. "
                "Cite most similar text fragment without change in main_fragment field."
            ),
        },
        {"role": "user", "content": text},
    ]
    try:
        completion = await asyncio.to_thread(
            client.chat.completions.parse,
            model=model,
            messages=messages,
            response_format=EvaluateResult,
        )
        result = completion.choices[0].message.parsed
        tokens = getattr(getattr(completion, "usage", None), "total_tokens", 0)
        if inst_name and stats is not None:
            stats.add_tokens(inst_name, tokens)
    except Exception as exc:  # pragma: no cover - external call
        logger.error("Failed to query OpenAI: %s", exc)
        result = EvaluateResult(similarity=0, main_fragment="")
    logger.debug("Prompt check: %s -> %s", prompt.name, result.similarity)
    return result
