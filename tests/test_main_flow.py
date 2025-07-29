import asyncio
import json
import logging
from types import SimpleNamespace

import pytest

import src.main as main


class BreakLoop(Exception):
    pass


@pytest.mark.asyncio
async def test_rescan_loop(monkeypatch):
    sleep_calls = []
    load_calls = []

    async def fake_sleep(t):
        sleep_calls.append(t)
        return None

    async def fake_update(inst, fr):
        raise BreakLoop

    def fake_load_config():
        load_calls.append(True)
        return {}

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main, "update_instance_chat_ids", fake_update)
    monkeypatch.setattr(main, "load_config", fake_load_config)

    inst = main.Instance(name="i", words=[], target_chat=0)
    with pytest.raises(BreakLoop):
        await main.rescan_loop(inst, interval=0)
    assert sleep_calls == [0]
    assert len(load_calls) == 1


@pytest.mark.asyncio
async def test_setup_logging(monkeypatch):
    recorded = {}

    def fake_basicConfig(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(logging, "basicConfig", fake_basicConfig)
    tele_logger = logging.getLogger("telethon")
    tele_logger.setLevel(logging.INFO)
    main.setup_logging("debug")
    assert recorded["level"] == logging.DEBUG
    assert tele_logger.level == logging.WARNING


@pytest.mark.asyncio
async def test_main_flow(monkeypatch, dummy_tg_client, dummy_message_cls, tmp_path):
    config = {"log_level": "info"}
    monkeypatch.setattr(main, "load_config", lambda: config)
    monkeypatch.setattr(main, "get_api_credentials", lambda cfg: (1, "h", "s"))

    dummy_client = dummy_tg_client
    monkeypatch.setattr(main, "TelegramClient", lambda s, a, b: dummy_client)

    stats_path = tmp_path / "stats.json"
    monkeypatch.setattr(
        main, "stats", main.StatsTracker(str(stats_path), flush_interval=0)
    )

    async def fake_rescan(inst):
        return None

    monkeypatch.setattr(main, "rescan_loop", fake_rescan)

    async def fake_update(inst, fr):
        inst.chat_ids = {1}

    monkeypatch.setattr(main, "update_instance_chat_ids", fake_update)

    async def fake_load_instances(cfg):
        return [
            main.Instance(name="i", words=["hi"], target_chat=99, target_entity="name")
        ]

    monkeypatch.setattr(main, "load_instances", fake_load_instances)

    async def fake_get_message_source(m):
        return "URL"

    monkeypatch.setattr(main, "get_message_source", fake_get_message_source)

    async def fake_get_chat_name(v, safe=False):
        return "name"

    monkeypatch.setattr(main, "get_chat_name", fake_get_chat_name)

    await main.main()
    assert main.config is config

    handler = dummy_client.on_handler
    msg = dummy_message_cls(SimpleNamespace(channel_id=1), msg_id=5, text="hi there")
    event = SimpleNamespace(message=msg, chat_id=1)
    await handler(event)
    assert msg.forwarded == [99, "name"]
    assert dummy_client.sent[0][0][0] == 99
    assert dummy_client.sent[1][0][0] == "name"
    data = json.loads(stats_path.read_text())
    assert data["total"] == 1
    inst = data["instances"][0]
    assert inst["name"] == "i"
    assert inst["total"] == 1


@pytest.mark.asyncio
async def test_process_message_prompt(monkeypatch, dummy_message_cls, tmp_path):
    sent = []

    class DummyClient:
        async def send_message(self, *a, **k):
            sent.append((a, k))

    main.client = DummyClient()
    main.stats = main.StatsTracker(str(tmp_path / "stats.json"), flush_interval=0)

    inst = main.Instance(
        name="p",
        words=[],
        prompts=[main.Prompt(name="hi", prompt="hi", threshold=4)],
        prompt_threshold=4,
        target_chat=1,
    )

    async def fake_match(prompts, text, threshold, inst_name):
        assert prompts == ["hi"]
        assert threshold == 4
        assert inst_name == "p"
        return 5

    async def fake_get_message_source(msg):
        return "src"

    async def fake_get_chat_name(v, safe=False):
        return "n"

    monkeypatch.setattr(main, "match_prompts", fake_match)
    monkeypatch.setattr(main, "get_message_source", fake_get_message_source)
    monkeypatch.setattr(main, "get_chat_name", fake_get_chat_name)

    msg = dummy_message_cls(SimpleNamespace(channel_id=1), msg_id=7, text="hi")
    event = SimpleNamespace(message=msg, chat_id=1)
    await main.process_message(inst, event)

    assert sent[0][0][0] == 1
    assert msg.forwarded == [1]
