"""Logits (classic knowledge) distillation mode.

Trains a local student model to match a white-box teacher's token distribution.

Config keys
-----------
teacher   : provider spec (must be white-box, e.g. ``provider: hf``)
student   : {"model": "<hf-id>", "device": ..., "load_in_4bit": bool}
data      : path to a ``*.samples.jsonl`` produced by the data mode
kd        : KDConfig dict (temperature, alpha, lr, epochs, output_dir, use_lora)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..agent.trajectory import read_jsonl
from ..providers.factory import build_provider
from ..train import KDConfig, KnowledgeDistillationTrainer, load_student_model
from .base import Mode, ModeResult, register_mode

__all__ = ["LogitsDistillationMode"]


@register_mode("logits")
class LogitsDistillationMode(Mode):
    name = "logits"

    def run(self) -> ModeResult:
        cfg = self.config
        teacher = build_provider(cfg.get("teacher"), default="hf")
        examples = self._load_examples(cfg)

        student_spec = cfg.get("student", {}) or {}
        model, tokenizer = load_student_model(student_spec)

        kd_cfg = KDConfig.from_dict(cfg.get("kd", {}) or {})
        trainer = KnowledgeDistillationTrainer(teacher, model, tokenizer, kd_cfg)
        result = trainer.train(examples)

        stats: Dict[str, Any] = {
            "teacher": f"{teacher.name}:{teacher.model}",
            "student": student_spec.get("model"),
            "temperature": kd_cfg.temperature,
            "alpha": kd_cfg.alpha,
            "avg_loss": result.get("avg_loss"),
            "optimizer_steps": result.get("optimizer_steps"),
        }
        return ModeResult(
            mode=self.name,
            output_path=kd_cfg.output_dir,
            num_examples=len(examples),
            stats=stats,
        )

    @staticmethod
    def _load_examples(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
        inline = cfg.get("examples")
        if inline:
            return list(inline)
        data_path = cfg.get("data")
        if not data_path:
            raise ValueError("logits mode requires 'data' (samples jsonl) or 'examples'")
        records = read_jsonl(Path(data_path))
        examples: List[Dict[str, Any]] = []
        for rec in records:
            if "prompt" in rec and "response" in rec:
                examples.append({"prompt": rec["prompt"], "response": rec["response"]})
            elif "messages" in rec:
                examples.append({"messages": rec["messages"]})
        if not examples:
            raise ValueError(f"no usable examples found in {data_path}")
        return examples
