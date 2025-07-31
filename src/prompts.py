import asyncio
import logging
from dataclasses import dataclass

import httpx

try:
    from langfuse import observe  # type: ignore
    from langfuse.openai import openai  # type: ignore
except Exception:  # pragma: no cover - optional integration
    import openai  # type: ignore

    def observe(*args, **kwargs):  # type: ignore[override]
        def decorator(func):
            return func

        return decorator


from typing import TYPE_CHECKING

from pydantic import BaseModel

from .stats import StatsTracker

if TYPE_CHECKING:  # pragma: no cover - used for type hints only
    from .config import Instance

langfuse = None

logger = logging.getLogger(__name__)

config: dict = {}
stats: StatsTracker | None = None


@dataclass
class Prompt:
    """Prompt description for LLM evaluation."""

    name: str | None = None
    prompt: str | None = None
    threshold: int = 4
    langfuse_name: str | None = None
    langfuse_label: str | None = None
    langfuse_version: int | None = None
    langfuse_type: str = "text"
    config: dict | None = None


def build_prompt(prompt: Prompt) -> str:
    """Construct final system prompt for LLM evaluation."""
    compiled = (
        f"{prompt.prompt}\n\n"
        "Evaluate message similarity: 0 - not match at all, 5 - strongly match. "
        "Cite most similar text fragment without change in main_fragment field."
    )
    prompt._compiled_prompt = compiled
    return compiled


async def load_langfuse_prompt(prompt: Prompt):
    """Populate ``prompt.prompt`` from Langfuse if ``langfuse_name`` is set.

    If the prompt doesn't exist in Langfuse it will be created. If the text in
    Langfuse differs from the one in the local config, a new version will be
    created and ``langfuse_version`` updated.
    """
    if langfuse is None or not prompt.langfuse_name:
        return None

    kwargs = {"type": prompt.langfuse_type}
    if prompt.langfuse_version is not None:
        kwargs["version"] = prompt.langfuse_version
    if prompt.langfuse_label is not None:
        kwargs["label"] = prompt.langfuse_label

    local_text = prompt.prompt

    try:
        lf_prompt = langfuse.get_prompt(prompt.langfuse_name, **kwargs)
    except Exception:  # pragma: no cover - optional external call
        try:
            lf_prompt = langfuse.create_prompt(
                name=prompt.langfuse_name,
                prompt=local_text or "",
                labels=[prompt.langfuse_label] if prompt.langfuse_label else [],
                type=prompt.langfuse_type,
                config=prompt.config,
            )
        except Exception as exc:  # pragma: no cover - optional external call
            logger.error(
                "Failed to create Langfuse prompt %s: %s", prompt.langfuse_name, exc
            )
            return None
    else:
        if local_text is not None and lf_prompt.prompt != local_text:
            try:
                lf_prompt = langfuse.create_prompt(
                    name=prompt.langfuse_name,
                    prompt=local_text,
                    labels=[prompt.langfuse_label] if prompt.langfuse_label else [],
                    type=prompt.langfuse_type,
                    config=prompt.config,
                )
            except Exception as exc:  # pragma: no cover - optional external call
                logger.error(
                    "Failed to create Langfuse prompt %s: %s", prompt.langfuse_name, exc
                )
                # fall back to fetched prompt

    prompt.prompt = lf_prompt.prompt
    prompt.langfuse_version = getattr(lf_prompt, "version", prompt.langfuse_version)
    prompt._lf_prompt = lf_prompt
    build_prompt(prompt)

    return lf_prompt


class EvaluateResult(BaseModel):
    """Result returned by LLM evaluation."""

    similarity: int
    main_fragment: str = ""


@observe()
async def match_prompt(
    prompt: Prompt,
    text: str,
    inst_name: str | None = None,
    chat_name: str | None = None,
) -> EvaluateResult:
    """Return :class:`EvaluateResult` for ``text`` using OpenAI."""
    if not prompt.prompt or not config.get("openai_api_key"):
        return EvaluateResult(similarity=0, main_fragment="")

    proxy = config.get("proxy_url")
    http_client = httpx.Client(proxy=proxy) if proxy else None
    client = openai.OpenAI(api_key=config["openai_api_key"], http_client=http_client)
    model = config.get("openai_model", "gpt-4.1-mini")

    if not getattr(prompt, "_compiled_prompt", None):
        build_prompt(prompt)

    messages = [
        {"role": "system", "content": prompt._compiled_prompt},
        {"role": "user", "content": text},
    ]
    try:
        metadata = {}
        tags = [t for t in [inst_name, chat_name] if t]
        if tags:
            metadata["langfuse_tags"] = tags
        extra = getattr(getattr(prompt, "_lf_prompt", None), "config", None) or {}
        params = {
            "model": extra.get("model", model),
            "messages": messages,
            "response_format": EvaluateResult,
            "metadata": metadata or None,
        }
        if "temperature" in extra:
            params["temperature"] = extra["temperature"]
        if "top_p" in extra:
            params["top_p"] = extra["top_p"]
        completion = await asyncio.to_thread(
            client.chat.completions.parse,
            **params,
        )
        result = completion.choices[0].message.parsed
        tokens = getattr(getattr(completion, "usage", None), "total_tokens", 0)
        if inst_name and stats is not None:
            stats.add_tokens(inst_name, tokens)
    except Exception as exc:  # pragma: no cover - external call
        logger.error("Failed to query OpenAI: %s", exc)
        result = EvaluateResult(similarity=0, main_fragment="")
    logger.debug("Prompt check: %s -> %s", prompt.name, result.similarity)

    if langfuse is not None:
        try:
            langfuse.update_current_generation(
                prompt=getattr(prompt, "_lf_prompt", None)
            )
            langfuse.update_current_trace(
                name=prompt.name,
                input=text,
                output=result.model_dump(),
            )
        except Exception as exc:  # pragma: no cover - optional external call
            logger.error("Failed to log Langfuse trace: %s", exc)

    return result


async def load_langfuse_prompts(instances: list["Instance"]) -> None:
    """Load prompt texts from Langfuse for all provided instances."""
    for inst in instances:
        for p in inst.prompts:
            await load_langfuse_prompt(p)
