import json
from types import SimpleNamespace

import pytest
import yaml

import src.evals as evals
import src.run_openai_evals as roe


class DummyFiles:
    def __init__(self):
        self.called = False

    def create(self, file, purpose):  # noqa: D401
        self.called = True
        return SimpleNamespace(id="file-1")


class DummyEvals:
    def __init__(self):
        self.created = None
        self.run_args = None
        self.runs = SimpleNamespace(create=self._runs_create)

    def create(self, **kwargs):
        self.created = kwargs
        return SimpleNamespace(id="eval-1")

    def _runs_create(self, eval_id, **kwargs):
        self.run_args = (eval_id, kwargs)
        return SimpleNamespace(report_url="url")


class DummyClient:
    def __init__(self):
        self.files = DummyFiles()
        self.evals = DummyEvals()


def test_run_openai_evals(tmp_path, monkeypatch):
    cfg = {
        "openai_api_key": "key",
        "instances": [
            {
                "name": "Inst",
                "words": [],
                "prompts": [
                    {
                        "name": "Prompt",
                        "prompt": "p",
                        "threshold": 3,
                        "config": {"temperature": 0.3, "model": "gpt-4.1"},
                    },
                ],
            }
        ],
    }
    cfg_path = tmp_path / "config.yml"
    cfg_path.write_text(yaml.dump(cfg), encoding="utf-8")

    base = evals.get_eval_path("Inst", "Prompt", "suf")
    base.mkdir(parents=True, exist_ok=True)
    with (base / "messages.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {"input": "good", "expected": {"is_match": True}, "trace_id": "t1"}
            )
            + "\n"
        )

    dummy = DummyClient()
    monkeypatch.setattr(roe, "OpenAI", lambda api_key=None: dummy)

    url = roe.run_openai_evals("Inst", "Prompt", "suf", config_path=str(cfg_path))
    assert url == "url"
    assert dummy.evals.created["name"] == "Inst_Prompt"
    assert (
        "def grade(sample, item):"
        in dummy.evals.created["testing_criteria"][0]["source"]
    )
    eval_id, run_kwargs = dummy.evals.run_args
    assert eval_id == "eval-1"
    ds = run_kwargs["data_source"]
    assert ds["model"] == "gpt-4.1"
    assert ds["sampling_params"]["temperature"] == 0.3
    assert (
        ds["sampling_params"]["response_format"]["json_schema"]["name"]
        == "EvaluateResult"
    )
    tmpl = ds["input_messages"]["template"]
    assert tmpl[0]["role"] == "system"
    assert "file_content" in ds["source"]["type"]
    assert len(ds["source"]["content"]) == 1
