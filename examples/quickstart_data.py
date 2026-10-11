"""Quickstart: response (data) distillation with a teacher model.

Runs fully offline using the built-in `echo` teacher. Swap `teacher` for a real
provider (openai / anthropic / hf / any OpenAI-compatible endpoint) to distil a
real model.

    python examples/quickstart_data.py
"""

from __future__ import annotations

from distill.modes import get_mode
from distill.providers.factory import build_provider
from distill.types import ChatMessage, SamplingParams


def main() -> None:
    teacher = build_provider({"provider": "echo", "model": "echo-1"})

    prompts = [
        "Explain knowledge distillation in two sentences.",
        "What is LoRA?",
        "Explain knowledge distillation in two sentences.",  # duplicate on purpose
    ]

    # 1) Generate, filter, dedupe and format training data.
    result = get_mode("data")(
        {
            "teacher": {"provider": "echo"},
            "prompts": prompts,
            "sampling": {"temperature": 0.8, "max_tokens": 128},
            "filters": [{"name": "non_empty"}, {"name": "length", "min_chars": 10}],
            "dedupe": {"exact": True, "near": {"enabled": True, "threshold": 0.9}},
            "format": "chat",
            "output": "runs/quickstart_data/data.jsonl",
        }
    ).run()

    print("data mode ->", result.num_examples, "examples")
    print("stats     ->", result.stats)

    # 2) Inspect a single teacher call directly.
    completion = teacher.chat(
        [ChatMessage.user("Give me one tip about fine-tuning.")],
        params=SamplingParams(temperature=0.0, max_tokens=64),
    )
    print("sample teacher response ->", completion.text)


if __name__ == "__main__":
    main()
