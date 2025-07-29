import asyncio
from types import SimpleNamespace

import pytest

import src.main as main


def test_word_in_text_basic():
    words = ["hello", "world"]
    assert main.word_in_text(words, "Hello there") is True
    assert main.word_in_text(words, "no match") is False


def test_get_message_url_object_peer(dummy_message_cls):
    peer = SimpleNamespace(channel_id=42)
    msg = dummy_message_cls(peer)
    assert main.get_message_url(msg) == "https://t.me/c/42/123"


def test_get_message_url_peerchannel(dummy_message_cls):
    peer = main.types.PeerChannel(7)
    msg = dummy_message_cls(peer)
    assert main.get_message_url(msg) == "https://t.me/c/7/123"


@pytest.mark.asyncio
async def test_get_message_source_url(monkeypatch, dummy_message_cls):
    peer = main.types.PeerChannel(8)
    msg = dummy_message_cls(peer)
    msg.chat = SimpleNamespace(username="chan")

    async def fake_get_chat_name(v, safe=False):
        return "chan"

    monkeypatch.setattr(main, "get_chat_name", fake_get_chat_name)
    res = await main.get_message_source(msg)
    assert res == "Forwarded from: @chan - https://t.me/c/8/123"


@pytest.mark.asyncio
async def test_get_message_source_text(monkeypatch, dummy_message_cls):
    peer = main.types.PeerChat(9)
    msg = dummy_message_cls(peer)
    msg.chat = SimpleNamespace(title="Group")

    async def fake_get_chat_name(v, safe=False):
        return "Group"

    monkeypatch.setattr(main, "get_chat_name", fake_get_chat_name)
    res = await main.get_message_source(msg)
    assert res == "Forwarded from: Group"


@pytest.mark.asyncio
async def test_get_message_source_private(monkeypatch, dummy_message_cls):
    peer = main.types.PeerUser(10)
    msg = dummy_message_cls(peer)
    msg.sender = SimpleNamespace(username="user")

    async def fake_get_chat_name(v, safe=False):
        return "user"

    monkeypatch.setattr(main, "get_chat_name", fake_get_chat_name)
    res = await main.get_message_source(msg)
    assert res == "Forwarded from: private @user"


def test_load_instances_direct():
    config = {
        "instances": [
            {
                "name": "test",
                "folders": ["f"],
                "chat_ids": [1],
                "entities": ["e"],
                "words": ["w"],
                "prompts": ["p"],
                "prompt_threshold": 3,
                "target_chat": 2,
                "target_entity": "@test",
            }
        ]
    }
    instances = asyncio.run(main.load_instances(config))
    assert len(instances) == 1
    inst = instances[0]
    assert inst.name == "test"
    assert inst.folders == ["f"]
    assert inst.chat_ids == {1}
    assert inst.entities == ["e"]
    assert inst.words == ["w"]
    assert inst.prompts == ["p"]
    assert inst.prompt_threshold == 3
    assert inst.target_chat == 2
    assert inst.target_entity == "@test"


def test_load_instances_backward_compat():
    config = {
        "folders": ["f"],
        "chat_ids": [1],
        "entities": ["e"],
        "words": ["w"],
        "target_chat": 2,
    }
    instances = asyncio.run(main.load_instances(config))
    assert len(instances) == 1
    inst = instances[0]
    assert inst.folders == ["f"]
    assert inst.chat_ids == {1}
    assert inst.entities == ["e"]
    assert inst.words == ["w"]
    assert inst.prompts == []
    assert inst.prompt_threshold == 4
    assert inst.target_chat == 2
    assert inst.target_entity is None


def test_load_instances_folder_mute():
    config = {
        "instances": [
            {
                "name": "m",
                "words": [],
                "folder_mute": True,
            }
        ]
    }
    instances = asyncio.run(main.load_instances(config))
    assert instances[0].folder_mute is True


@pytest.mark.asyncio
async def test_match_prompts_iter(monkeypatch):
    calls = []

    class DummyCompletions:
        def parse(self, *, model=None, messages=None, response_format=None, response_model=None):  # noqa: D401 - test stub
            prompt = messages[0]["content"].split("\n", 1)[0]
            calls.append(prompt)
            score = {"p1": 3, "p2": 5}[prompt]
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            parsed=SimpleNamespace(similarity=score)
                        )
                    )
                ]
            )

    class DummyClient:
        def __init__(self, api_key=None, http_client=None):  # noqa: D401 - test stub
            self.chat = SimpleNamespace(completions=DummyCompletions())

    monkeypatch.setattr(main, "OpenAI", DummyClient)
    main.config["openai_api_key"] = "k"
    result = await main.match_prompts(["p1", "p2"], "msg", 4, "i")
    assert result == 5
    assert calls == ["p1", "p2"]


@pytest.mark.asyncio
async def test_match_prompts_iter_stop(monkeypatch):
    calls = []

    class DummyCompletions:
        def parse(self, *, model=None, messages=None, response_format=None, response_model=None):  # noqa: D401 - test stub
            prompt = messages[0]["content"].split("\n", 1)[0]
            calls.append(prompt)
            score = {"p1": 5, "p2": 0}[prompt]
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            parsed=SimpleNamespace(similarity=score)
                        )
                    )
                ]
            )

    class DummyClient:
        def __init__(self, api_key=None, http_client=None):  # noqa: D401 - test stub
            self.chat = SimpleNamespace(completions=DummyCompletions())

    monkeypatch.setattr(main, "OpenAI", DummyClient)
    main.config["openai_api_key"] = "k"
    result = await main.match_prompts(["p1", "p2"], "msg", 4, "i")
    assert result == 5
    assert calls == ["p1"]
