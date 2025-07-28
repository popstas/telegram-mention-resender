import asyncio
from types import SimpleNamespace

import pytest

import src.main as main


@pytest.mark.asyncio
async def test_get_chat_name_with_cache_and_client(monkeypatch):
    calls = []

    class DummyClient:
        async def get_entity(self, ident):
            calls.append(ident)
            return SimpleNamespace(title="Chat Name")

    main.client = DummyClient()
    main.entity_name_cache.clear()

    name = await main.get_chat_name("id1", safe=True)
    assert name == "Chat_Name"
    # Second call should hit cache and not call client again
    name2 = await main.get_chat_name("id1", safe=True)
    assert name2 == "Chat_Name"
    assert calls == ["id1"]


@pytest.mark.asyncio
async def test_get_chat_name_error(monkeypatch):
    class FailClient:
        async def get_entity(self, ident):
            raise RuntimeError("fail")

    main.client = FailClient()
    main.entity_name_cache.clear()

    name = await main.get_chat_name("https://t.me/testchat?param=1", safe=True)
    assert name == "testchat"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity,expected",
    [
        (SimpleNamespace(first_name="First", last_name="Last"), "First_Last"),
        (SimpleNamespace(username="user.name"), "user.name"),
        (SimpleNamespace(id=42), "42"),
    ],
)
async def test_get_chat_name_various(monkeypatch, entity, expected):
    class DummyClient:
        async def get_entity(self, ident):
            return entity

    main.client = DummyClient()
    main.entity_name_cache.clear()
    result = await main.get_chat_name("identifier", safe=True)
    assert result == expected


@pytest.mark.asyncio
async def test_get_chat_name_empty_identifier(monkeypatch):
    result = await main.get_chat_name("", safe=True)
    assert result == "chat_history"


@pytest.mark.asyncio
async def test_get_chat_name_plus_link(monkeypatch):
    class DummyClient:
        async def get_entity(self, ident):
            raise ValueError("not found")

    main.client = DummyClient()
    main.entity_name_cache.clear()
    result = await main.get_chat_name("https://t.me/+abcDEF123", safe=True)
    assert result == "invite_abcDEF123"


@pytest.mark.asyncio
async def test_resolve_entities(monkeypatch):
    calls = []

    class DummyClient:
        async def get_entity(self, ent):
            calls.append(ent)
            if ent == "bad":
                raise RuntimeError("fail")
            return SimpleNamespace(id=int(ent))

    main.client = DummyClient()
    monkeypatch.setattr(main, "get_peer_id", lambda e: e.id)

    result = await main.resolve_entities(["1", "bad", "2", "1"])
    assert result == {1, 2}
    assert calls == ["1", "bad", "2", "1"]


@pytest.mark.asyncio
async def test_get_entity_name_from_int(monkeypatch):
    recorded = []

    class DummyClient:
        async def get_entity(self, ident):
            recorded.append(type(ident))
            return SimpleNamespace(title="Chat")

    main.client = DummyClient()
    name = await main.get_entity_name(-1000000000042, safe=True)
    assert name == "Chat"
    assert recorded and issubclass(recorded[0], main.types.PeerChannel)


def test_get_safe_name():
    assert main.get_safe_name("A B") == "A_B"
