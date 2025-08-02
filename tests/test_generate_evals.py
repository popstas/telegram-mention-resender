import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import src.config as config_module
import src.generate_evals as ge


class DummyMessage:
    def __init__(self, text: str):
        self.text = text
        self.message = text
        self.raw_text = text


class DummyClient:
    def __init__(self, messages):
        self._messages = messages

    async def start(self):
        return self

    async def disconnect(self):
        return None

    async def iter_messages(self, entity):
        for text in self._messages.get(entity, []):
            yield DummyMessage(text)


@pytest.mark.asyncio
async def test_generate_evals(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    cfg_path = tmp_path / "config.yml"
    monkeypatch.setattr(config_module, "CONFIG_PATH", cfg_path)

    cfg = {
        "api_id": 1,
        "api_hash": "hash",
        "session": "session",
        "instances": [
            {
                "name": "Inst",
                "true_positive_entity": "pos",
                "false_positive_entity": "neg",
                "words": [],
                "prompts": [
                    {
                        "name": "Prompt",
                        "prompt": "prompt text",
                        "threshold": 3,
                        "config": {"model": "gpt-4.1", "temperature": 0.2},
                    }
                ],
            }
        ],
    }
    cfg_path.write_text(yaml.dump(cfg), encoding="utf-8")

    msgs = {"pos": ["p1", "p2"], "neg": ["n1"]}
    monkeypatch.setattr(ge, "TelegramClient", lambda *a, **k: DummyClient(msgs))

    await ge.generate_evals("suf")

    base = Path("data/evals/Inst_Prompt_suf")
    data = base / "messages.jsonl"
    assert data.exists()
    lines = [json.loads(l) for l in data.read_text(encoding="utf-8").splitlines()]
    assert lines == [
        {"input": "p1", "expected": {"is_match": True}},
        {"input": "p2", "expected": {"is_match": True}},
        {"input": "n1", "expected": {"is_match": False}},
    ]
    task = (base / "task.yml").read_text(encoding="utf-8")
    assert "eval_name: Inst_Prompt" in task
    assert "score >= 3" in task
