import json
import sys
from types import SimpleNamespace

import pytest
import yaml

import src.evals as evals
import src.prompts as prompts
import src.run_deepeval as rd


@pytest.mark.asyncio
async def test_run_deepeval(tmp_path, monkeypatch):
    cfg = {
        "instances": [
            {
                "name": "Inst",
                "words": [],
                "prompts": [
                    {"name": "Prompt", "prompt": "p", "threshold": 2},
                ],
            }
        ]
    }
    cfg_path = tmp_path / "config.yml"
    cfg_path.write_text(yaml.dump(cfg), encoding="utf-8")

    base = evals.get_eval_path("Inst", "Prompt", "suf")
    base.mkdir(parents=True, exist_ok=True)
    messages = [
        {"input": "good", "expected": {"is_match": True}, "trace_id": "t1"},
        {"input": "bad", "expected": {"is_match": False}, "trace_id": "t2"},
    ]
    with (base / "messages.jsonl").open("w", encoding="utf-8") as fh:
        for row in messages:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    async def fake_match_prompt(prompt, text, inst_name=None, chat_name=None):
        score = 3 if text == "good" else 1
        return SimpleNamespace(
            score=score,
            reasoning=f"rsn {text}",
            quote=f"qt {text}",
            token_cost=1.0,
            completion_time=2.0,
        )

    monkeypatch.setattr(prompts, "match_prompt", fake_match_prompt)

    created: list[SimpleNamespace] = []

    class DummyTC(SimpleNamespace):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            created.append(self)

    def fake_evaluate(test_cases, metrics):
        metric = metrics[0]
        results = []
        for tc in test_cases:
            metric.measure(tc)
            results.append(SimpleNamespace(success=metric.success))
        return SimpleNamespace(test_results=results)

    class DummyBaseMetric:
        def __init__(self, name=None):
            self.name = name

    monkeypatch.setattr(rd, "LLMTestCase", DummyTC)
    monkeypatch.setattr(rd, "evaluate", fake_evaluate)
    monkeypatch.setattr(rd, "BaseMetric", DummyBaseMetric)

    acc = await rd.run_deepeval("Inst", "Prompt", "suf", config_path=str(cfg_path))
    assert acc == 1.0
    assert created[0].comments == "rsn good"
    assert created[0].context == ["qt good"]
    assert created[0].token_cost == 1.0
    assert created[0].completion_time == 2.0


def test_main_exit_code(monkeypatch):
    async def fake_run_deepeval(instance, prompt_name, suffix, *, config_path=None):
        return 0.5

    monkeypatch.setattr(rd, "run_deepeval", fake_run_deepeval)
    monkeypatch.setattr(
        sys,
        "argv",
        ["rd", "--instance", "i", "--prompt", "p", "--suffix", "s"],
    )
    with pytest.raises(SystemExit) as exc:
        rd.main()
    assert exc.value.code == 1
