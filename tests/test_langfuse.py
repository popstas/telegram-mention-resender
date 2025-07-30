import asyncio
import os
from types import SimpleNamespace

import pytest

import src.langfuse_utils as lfu
import src.prompts as prompts


class DummyLangfuse:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.traces = []

    def update_current_trace(self, **kwargs):
        self.traces.append(kwargs)


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
    assert os.environ["LANGFUSE_PUBLIC_KEY"] == "pk"
    assert os.environ["LANGFUSE_SECRET_KEY"] == "sk"
    assert os.environ["LANGFUSE_HOST"] == "url"


@pytest.mark.asyncio
async def test_match_prompt_logs(monkeypatch):
    dummy = DummyLangfuse()
    monkeypatch.setattr(prompts, "langfuse", dummy)
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
    assert dummy.traces[0]["name"] == "p"
    assert dummy.traces[0]["input"] == "text"
    assert dummy.traces[0]["output"] == result_obj.model_dump()
    assert recorded["metadata"] == {"langfuse_tags": ["i", "c"]}
