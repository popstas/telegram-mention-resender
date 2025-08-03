import argparse
import asyncio
import json
import os

from . import langfuse_utils, prompts
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


async def run_prompt_match(prompt, text: str):
    """Run prompt match and return raw :class:`EvaluateResult`."""
    return await prompts.match_prompt(prompt, text)


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
    global langfuse
    langfuse = langfuse_utils.init_langfuse(config)
    prompts.langfuse = langfuse
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

        res = await run_prompt_match(prompt, row["input"])
        test_cases.append(
            LLMTestCase(
                input=row["input"],
                actual_output=("true" if res.score >= prompt.threshold else "false"),
                expected_output=str(row["expected"]["is_match"]).lower(),
                comments=res.reasoning or None,
                context=[res.quote] if res.quote else None,
                token_cost=getattr(res, "token_cost", None),
                completion_time=getattr(res, "completion_time", None),
            )
        )

    class BoolAccuracyMetric(BaseMetric):
        """Проверяет, совпадает ли булев verdict модели с эталоном."""

        def __init__(self, prompt=None, *, threshold: float = 0.5):
            self.threshold = threshold  # обязателен
            self.include_reason = True
            self.async_mode = True
            self._prompt = prompt

            # будут заполнены позже
            self.score = 0.0
            self.reason = ""
            self.success = False
            self.error = None

        def measure(self, test_case: LLMTestCase) -> float:
            try:
                # actual_output is now a string "true"/"false"
                actual_bool = test_case.actual_output == "true"
                expected_bool = test_case.expected_output == "true"

                self.score = 1.0 if actual_bool == expected_bool else 0.0
                self.reason = (
                    "match" if self.score else f"exp={expected_bool}, got={actual_bool}"
                )
                self.success = self.score >= self.threshold
                return self.score
            except Exception as exc:
                self.error = str(exc)
                self.success = False
                raise

        async def a_measure(self, test_case: LLMTestCase) -> float:  # noqa: D401
            # For consistency, we'll just call measure since it doesn't need async operations
            return self.measure(test_case)

        def is_successful(self) -> bool:  # noqa: D401
            return self.success and self.error is None

        @property
        def __name__(self) -> str:  # noqa: D401
            return "Boolean Accuracy"

    metric = BoolAccuracyMetric(prompt)
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
    if accuracy < 0.8:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
