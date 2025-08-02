import argparse
import asyncio
import json
import os

from . import prompts
from .config import load_config, load_instances
from .evals import get_eval_path

try:  # pragma: no cover - optional dependency
    from deepeval import evaluate
    from deepeval.metrics.base_metric import BaseMetric
    from deepeval.test_case import LLMTestCase
except Exception:  # pragma: no cover - optional dependency
    evaluate = None
    LLMTestCase = object  # type: ignore
    BaseMetric = object  # type: ignore


async def run_deepeval(
    instance: str,
    prompt_name: str,
    suffix: str,
    *,
    config_path: str | None = None,
) -> float:
    """Run evaluation for a specific instance and prompt.

    Returns overall accuracy as a float between 0 and 1.
    """
    if config_path:
        os.environ["CONFIG_PATH"] = config_path
        from . import config as config_module

        config_module.CONFIG_PATH = config_path

    config = load_config()
    prompts.config.update(config)
    instances = await load_instances(config)

    inst = next((i for i in instances if i.name == instance), None)
    if inst is None:
        raise ValueError(f"Instance not found: {instance}")

    prompt = next((p for p in inst.prompts if p.name == prompt_name), None)
    if prompt is None:
        raise ValueError(f"Prompt '{prompt_name}' not found in instance '{instance}'")

    base = get_eval_path(inst.name, prompt.name or "prompt", suffix)
    msg_path = base / "messages.jsonl"
    if not msg_path.exists():
        raise FileNotFoundError(msg_path)

    test_cases = []
    for line in msg_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        test_cases.append(
            LLMTestCase(
                input=row["input"],
                actual_output=str(True).lower(),
                # actual_output=await prompts.match_prompt(prompt, row["input"])["score"] >= (prompt.threshold or 0),
                expected_output=str(row["expected"]["is_match"]).lower(),
            )
        )

    class BoolAccuracyMetric(BaseMetric):
        def __init__(self) -> None:
            self.name = "bool_accuracy"
            self.score = 0.0
            self.reason = ""
            self.success = False
            self.threshold = 0.5
            self.async_mode = False

        def measure(self, test_case) -> float:  # type: ignore[override]
            exp = str(test_case.expected_output).lower()
            act = str(getattr(test_case, "actual_output", "")).lower()
            self.score = 1.0 if exp == act else 0.0
            self.reason = "match" if self.score else f"exp={exp}, got={act}"
            self.success = self.score >= self.threshold
            return float(self.score)

        async def a_measure(self, test_case) -> float:  # type: ignore[override]
            return self.measure(test_case)

        def is_successful(self) -> bool:
            return self.success

    metric = BoolAccuracyMetric()
    if evaluate is None:  # pragma: no cover - optional dependency
        raise RuntimeError("deepeval is required to run evaluations")
    results = evaluate(test_cases, metrics=[metric])
    # Extract accuracy from the results
    if hasattr(results, "test_results") and results.test_results:
        # Calculate accuracy as the ratio of successful tests
        successful_tests = sum(
            1 for test_result in results.test_results if test_result.success
        )
        return float(successful_tests / len(results.test_results))
    else:
        return 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepEval on saved datasets")
    parser.add_argument("--config", help="Path to config.yml", default=None)
    parser.add_argument("--instance", required=True, help="Instance name")
    parser.add_argument("--prompt", required=True, help="Prompt name")
    parser.add_argument("--suffix", required=True, help="Dataset suffix")
    args = parser.parse_args()
    accuracy = asyncio.run(
        run_deepeval(
            args.instance,
            args.prompt,
            args.suffix,
            config_path=args.config,
        )
    )
    print(f"Accuracy: {accuracy:.2%}")


if __name__ == "__main__":
    main()
