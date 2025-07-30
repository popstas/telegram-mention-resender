import asyncio
from types import SimpleNamespace

import pytest

import src.langfuse_utils as lfu
import src.prompts as prompts


class DummyLangfuse:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.events = []

    def create_event(self, **kwargs):
        self.events.append(kwargs)


def test_init_langfuse(monkeypatch):
    recorded = {}

    def fake_langfuse(**kwargs):
        recorded.update(kwargs)
        return "client"

    monkeypatch.setattr(lfu, "Langfuse", fake_langfuse)
    cfg = {
        "langfuse_public_key": "pk",
        "langfuse_secret_key": "sk",
        "langfuse_base_url": "url",
    }
    client = lfu.init_langfuse(cfg)
    assert client == "client"
    assert recorded == {"public_key": "pk", "secret_key": "sk", "host": "url"}


@pytest.mark.asyncio
async def test_match_prompt_logs(monkeypatch):
    dummy = DummyLangfuse()
    prompts.langfuse_client = dummy
    prompts.config["openai_api_key"] = "k"

    result_obj = prompts.EvaluateResult(similarity=4, main_fragment="f")

    recorded = {}

    class DummyCompletions:
        def parse(self, **kwargs):
            recorded.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(parsed=result_obj))]
            )

    class DummyClient:
        def __init__(self, api_key=None, http_client=None):
            self.chat = SimpleNamespace(completions=DummyCompletions())

    monkeypatch.setattr(prompts.openai, "OpenAI", DummyClient)

    prompt = prompts.Prompt(name="p", prompt="p")
    res = await prompts.match_prompt(prompt, "text", "i", "c")

    assert res == result_obj
    assert dummy.events[0]["name"] == "p"
    assert dummy.events[0]["input"] == {"prompt": "p", "text": "text"}
    assert dummy.events[0]["output"] == result_obj.model_dump()
    assert recorded["metadata"] == {"langfuse_tags": ["i", "c"]}
