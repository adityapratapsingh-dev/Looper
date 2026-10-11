"""Compare a teacher and a student (offline, echo provider).

Shows the evaluation harness for text prompts and for agent tasks.

    python examples/eval_teacher_student.py
"""

from __future__ import annotations

from distill.agent import RunConfig, default_registry
from distill.eval import Evaluator
from distill.providers import get_provider
from distill.types import SamplingParams


def main() -> None:
    teacher = get_provider("echo", model="echo-teacher")
    student = get_provider("echo", model="echo-student")  # stand-in for a distilled model

    evaluator = Evaluator(teacher, student, params=SamplingParams(temperature=0.7, max_tokens=128))

    text_result = evaluator.evaluate_prompts(
        ["Explain distillation.", "What is an agent?"],
        system_prompt="Be concise.",
    )
    print("text metrics:")
    for k, v in text_result.metrics.items():
        print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")

    agent_result = evaluator.evaluate_agents(
        ["search for lora", "calculate 21 * 2"],
        default_registry(),
        run_config=RunConfig(max_steps=4),
        verify_fn=lambda t: bool(t.messages[-1].content.strip()),
        reward_fn=lambda t: 1.0 if t.success else 0.0,
    )
    print("\nagent metrics:")
    for k, v in agent_result.metrics.items():
        print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")


if __name__ == "__main__":
    main()
