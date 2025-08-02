import json
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
        {"input": "good", "expected": {"is_match": True}},
        {"input": "bad", "expected": {"is_match": False}},
    ]
    with (base / "messages.jsonl").open("w", encoding="utf-8") as fh:
        for row in messages:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    async def fake_match_prompt(prompt, text, inst_name=None, chat_name=None):
        score = 3 if text == "good" else 1
        return prompts.EvaluateResult(score=score, reasoning="", quote="")

    monkeypatch.setattr(prompts, "match_prompt", fake_match_prompt)

    class DummyTC:
        def __init__(self, input, actual_output, expected_output):
            self.input = input
            self.actual_output = actual_output
            self.expected_output = expected_output

    async def fake_evaluate(test_cases, metrics):
        metric = metrics[0]
        results = []
        for tc in test_cases:
            await metric.a_measure(tc)
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
