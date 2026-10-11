"""Supervised fine-tuning (SFT) trainer for distilled datasets.

This is the training step that consumes the output of the *data* and *agent*
modes: a student is fine-tuned on teacher-generated responses (and, for agents,
on the teacher's tool-use trajectories).

Examples may be given as:
* ``{"prompt": [messages], "response": {message}}`` (from data mode), or
* ``{"messages": [ ... full conversation ... ]}`` (from agent/text formats) —
  in which case the last assistant turn is treated as the target and everything
  before it as the prompt.

Requires ``torch`` / ``transformers``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from ..errors import MissingDependencyError
from ..types import ChatMessage, Role

__all__ = ["SFTConfig", "SupervisedFineTuneTrainer", "split_messages"]


def split_messages(messages: Sequence[ChatMessage]):
    """Split a conversation into (prompt, target_text) for SFT."""

    idx = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == Role.ASSISTANT:
            idx = i
            break
    if idx is None:
        return list(messages), messages[-1].text() if messages else ""
    return list(messages[:idx]), messages[idx].text()


@dataclass
class SFTConfig:
    lr: float = 2e-5
    epochs: int = 1
    batch_size: int = 1
    grad_accum: int = 1
    max_length: int = 1024
    output_dir: str = "runs/sft"
    use_lora: bool = False
    lora_r: int = 16
    lora_alpha: int = 32
    log_every: int = 10
    device: Optional[str] = None
    seed: int = 0

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SFTConfig":
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


class SupervisedFineTuneTrainer:
    """A small, dependency-light SFT loop (LoRA optional)."""

    def __init__(self, model: Any, tokenizer: Any, config: Optional[SFTConfig] = None) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.config = config or SFTConfig()
        self.history: List[Dict[str, float]] = []

    def _render(self, messages: Sequence[ChatMessage]) -> str:
        msgs = [m.to_dict() for m in messages]
        if getattr(self.tokenizer, "chat_template", None):
            try:
                return self.tokenizer.apply_chat_template(
                    msgs, tokenize=False, add_generation_prompt=False
                )
            except Exception:  # noqa: BLE001
                pass
        return "\n".join(f"{m['role']}: {m.get('content','')}" for m in msgs)

    def _example_to_prompt_target(self, ex: Dict[str, Any]):
        if "messages" in ex:
            msgs = [ChatMessage.from_dict(m) for m in ex["messages"]]
            return split_messages(msgs)
        prompt = [ChatMessage.from_dict(m) for m in ex.get("prompt", [])]
        resp = ex.get("response", {})
        target = resp.get("content", "") if isinstance(resp, dict) else str(resp)
        return prompt, target

    def _encode(self, prompt_messages, target_text):
        import torch

        prompt_text = self._render(prompt_messages)
        p_ids = self.tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
        t_ids = self.tokenizer(target_text, add_special_tokens=False)["input_ids"]
        if getattr(self.tokenizer, "eos_token_id", None) is not None:
            t_ids = t_ids + [self.tokenizer.eos_token_id]
        input_ids = (p_ids + t_ids)[: self.config.max_length]
        labels = ([-100] * len(p_ids) + t_ids)[: self.config.max_length]
        return (
            torch.tensor([input_ids]),
            torch.tensor([[1] * len(input_ids)]),
            torch.tensor([labels]),
        )

    def _prepare(self) -> None:
        try:
            import torch  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            raise MissingDependencyError("torch", "train") from exc
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        if self.config.use_lora:
            try:
                from peft import LoraConfig, get_peft_model  # type: ignore
            except Exception as exc:  # noqa: BLE001
                raise MissingDependencyError("peft", "train") from exc
            self.model = get_peft_model(
                self.model,
                LoraConfig(
                    r=self.config.lora_r,
                    lora_alpha=self.config.lora_alpha,
                    lora_dropout=0.05,
                    bias="none",
                    task_type="CAUSAL_LM",
                ),
            )
        self.model.train()

    def train(self, examples: List[Dict[str, Any]]) -> Dict[str, Any]:
        import torch

        self._prepare()
        torch.manual_seed(self.config.seed)
        device = self.config.device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(device)

        optimizer = torch.optim.AdamW(
            [p for p in self.model.parameters() if p.requires_grad], lr=self.config.lr
        )
        steps = 0
        optimizer.zero_grad()
        for epoch in range(self.config.epochs):
            running = 0.0
            for i, ex in enumerate(examples):
                prompt, target = self._example_to_prompt_target(ex)
                input_ids, attn, labels = self._encode(prompt, target)
                input_ids, attn, labels = (
                    input_ids.to(device),
                    attn.to(device),
                    labels.to(device),
                )
                out = self.model(input_ids=input_ids, attention_mask=attn, labels=labels)
                loss = out.loss
                (loss / self.config.grad_accum).backward()
                if (i + 1) % self.config.grad_accum == 0:
                    optimizer.step()
                    optimizer.zero_grad()
                    steps += 1
                running += float(loss.detach())
                if self.config.log_every and (i + 1) % self.config.log_every == 0:
                    self.history.append(
                        {"epoch": epoch, "step": i + 1, "loss": running / (i + 1)}
                    )
            optimizer.step()
            optimizer.zero_grad()

        self._save()
        avg = (sum(h["loss"] for h in self.history) / len(self.history)) if self.history else None
        return {
            "epochs": self.config.epochs,
            "examples": len(examples),
            "optimizer_steps": steps,
            "avg_loss": avg,
            "output_dir": self.config.output_dir,
            "history": self.history,
        }

    def _save(self) -> None:
        import os

        os.makedirs(self.config.output_dir, exist_ok=True)
        self.model.save_pretrained(self.config.output_dir)
        self.tokenizer.save_pretrained(self.config.output_dir)

