import asyncio

import pytest
from telethon.errors import TypeNotFoundError

import src.app as app


class FakeClient:
    """Minimal stand-in for TelegramClient.

    Mirrors the parts of the Telethon API exercised by
    ``run_until_disconnected_resilient``: connected/disconnected state, an
    ``_updates_error`` slot, and a ``run_until_disconnected`` coroutine whose
    behaviour is scripted by the test.
    """

    def __init__(self, behaviours):
        self._behaviours = list(behaviours)
        self.calls = 0
        self._connected = True
        self.connect_calls = 0
        self._updates_error = None

    def is_connected(self):
        return self._connected

    async def connect(self):
        self.connect_calls += 1
        self._connected = True

    async def run_until_disconnected(self):
        self.calls += 1
        behaviour = self._behaviours.pop(0)
        self._connected = False  # Telethon's finally-block disconnects
        if isinstance(behaviour, BaseException):
            raise behaviour
        return behaviour


@pytest.mark.asyncio
async def test_resilient_loop_restarts_on_unknown_constructor(monkeypatch):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    client = FakeClient(
        behaviours=[TypeNotFoundError(0x3AE56482, b""), None],
    )

    await app.run_until_disconnected_resilient(client, backoff_seconds=0.0)

    assert client.calls == 2
    assert client.connect_calls == 1  # reconnected after the first failure
    assert sleeps == [0.0]
    assert client._updates_error is None


@pytest.mark.asyncio
async def test_resilient_loop_propagates_other_errors(monkeypatch):
    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    client = FakeClient(behaviours=[RuntimeError("boom")])

    with pytest.raises(RuntimeError, match="boom"):
        await app.run_until_disconnected_resilient(client, backoff_seconds=0.0)

    assert client.calls == 1
