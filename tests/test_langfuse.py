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
        self.generations = []

    def update_current_trace(self, **kwargs):
        self.traces.append(kwargs)

    def update_current_generation(self, **kwargs):  # noqa: D401 - test stub
        self.generations.append(kwargs)


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
    os.environ["OTEL_SDK_DISABLED"] = "1"
    client = lfu.init_langfuse(cfg)
    assert client == "client"
    assert recorded == {"public_key": "pk", "secret_key": "sk", "host": "url"}
    assert os.environ["LANGFUSE_PUBLIC_KEY"] == "pk"
    assert os.environ["LANGFUSE_SECRET_KEY"] == "sk"
    assert os.environ["LANGFUSE_HOST"] == "url"
    os.environ.pop("OTEL_SDK_DISABLED", None)
    os.environ.pop("LANGFUSE_HOST", None)


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
    assert "prompt" not in dummy.traces[0]
    assert dummy.generations[0]["prompt"] is None
    assert recorded["metadata"] == {"langfuse_tags": ["i", "c"]}


@pytest.mark.asyncio
async def test_load_langfuse_prompt(monkeypatch):
    recorded = {}

    class DummyClient:
        def get_prompt(self, name, **kwargs):  # noqa: D401 - test stub
            recorded["name"] = name
            recorded["kwargs"] = kwargs
            return SimpleNamespace(prompt="loaded", version=1)

    monkeypatch.setattr(prompts, "langfuse", DummyClient())

    p = prompts.Prompt(langfuse_name="n", langfuse_label="prod")
    lf = await prompts.load_langfuse_prompt(p)
    assert p.prompt == "loaded"
    assert p.langfuse_version == 1
    assert p._lf_prompt is lf
    assert recorded["name"] == "n"
    assert recorded["kwargs"] == {"type": "text", "label": "prod"}


@pytest.mark.asyncio
async def test_load_langfuse_prompt_create(monkeypatch):
    recorded = {}

    class DummyClient:
        def get_prompt(self, *a, **k):  # noqa: D401 - test stub
            raise Exception("404")

        def create_prompt(self, **kwargs):  # noqa: D401 - test stub
            recorded.update(kwargs)
            return SimpleNamespace(prompt=kwargs["prompt"], version=2)

    monkeypatch.setattr(prompts, "langfuse", DummyClient())

    p = prompts.Prompt(
        langfuse_name="n",
        langfuse_label="prod",
        prompt="text",
        config={"model": "gpt"},
    )
    lf = await prompts.load_langfuse_prompt(p)
    assert p.prompt == "text"
    assert p.langfuse_version == 2
    assert p._lf_prompt is lf
    assert recorded["name"] == "n"
    assert recorded["labels"] == ["prod"]
    assert recorded["type"] == "text"
    assert recorded["config"] == {"model": "gpt"}


@pytest.mark.asyncio
async def test_load_langfuse_prompt_new_version(monkeypatch):
    calls = {}

    class DummyClient:
        def get_prompt(self, *a, **k):  # noqa: D401 - test stub
            return SimpleNamespace(prompt="old", version=1)

        def create_prompt(self, **kwargs):  # noqa: D401 - test stub
            calls.update(kwargs)
            return SimpleNamespace(prompt=kwargs["prompt"], version=3)

    monkeypatch.setattr(prompts, "langfuse", DummyClient())

    p = prompts.Prompt(
        langfuse_name="n",
        langfuse_label="prod",
        prompt="new",
    )
    lf = await prompts.load_langfuse_prompt(p)
    assert p.prompt == "new"
    assert p.langfuse_version == 3
    assert p._lf_prompt is lf
    assert calls["prompt"] == "new"
    assert calls["name"] == "n"
    assert calls["labels"] == ["prod"]


@pytest.mark.asyncio
async def test_match_prompt_lf_config(monkeypatch):
    dummy = DummyLangfuse()
    monkeypatch.setattr(prompts, "langfuse", dummy)
    prompts.config["openai_api_key"] = "k"

    result_obj = prompts.EvaluateResult(similarity=3, main_fragment="f")
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

    lf_prompt = SimpleNamespace(config={"temperature": 0.1})
    p = prompts.Prompt(name="p", prompt="p")
    p._lf_prompt = lf_prompt

    res = await prompts.match_prompt(p, "text")

    assert res == result_obj
    assert recorded["temperature"] == 0.1
    assert dummy.generations[0]["prompt"] is lf_prompt
    assert "prompt" not in dummy.traces[0]
    assert hasattr(p, "_compiled_prompt")
