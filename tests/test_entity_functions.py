import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import asyncio
from types import SimpleNamespace

import pytest

import src.main as main


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity,expected",
    [
        (SimpleNamespace(first_name="First", last_name="Last"), "First_Last"),
        (SimpleNamespace(username="user.name"), "user.name"),
        (SimpleNamespace(id=42), "42"),
    ],
)
async def test_get_entity_name_various(monkeypatch, entity, expected):
    class DummyClient:
        async def get_entity(self, ident):
            return entity

    main.client = DummyClient()
    main.entity_name_cache.clear()
    result = await main.get_entity_name("identifier")
    assert result == expected


@pytest.mark.asyncio
async def test_get_entity_name_empty_identifier(monkeypatch):
    result = await main.get_entity_name("")
    assert result == "chat_history"


@pytest.mark.asyncio
async def test_get_entity_name_plus_link(monkeypatch):
    class DummyClient:
        async def get_entity(self, ident):
            raise ValueError("not found")

    main.client = DummyClient()
    main.entity_name_cache.clear()
    result = await main.get_entity_name("https://t.me/+abcDEF123")
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
