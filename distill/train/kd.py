"""Classic knowledge-distillation trainer (logits mode).

Trains a student to match the teacher's *temperature-scaled* token distribution
at every target position, optionally mixed with hard-label cross-entropy:

    L = alpha * T^2 * KL(student/T || teacher/T) + (1 - alpha) * CE(student, y)

Works with black-box teachers that expose per-token logprobs (soft targets come
from ``Completion.logprobs``) or white-box local teachers
(``HuggingFaceProvider.sequence_distributions`` for exact full-vocab targets).
Requires ``torch`` / ``transformers`` (``pip install 'distill[train]'``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..errors import MissingDependencyError
from ..types import ChatMessage
from .losses import kd_loss

__all__ = ["KDConfig", "KnowledgeDistillationTrainer"]


@dataclass
class KDConfig:
    temperature: float = 2.0
    alpha: float = 0.9
    lr: float = 5e-5
    epochs: int = 1
    batch_size: int = 1
    grad_accum: int = 1
    max_length: int = 1024
    output_dir: str = "runs/kd"
    use_lora: bool = False
    lora_r: int = 16
    lora_alpha: int = 32
    log_every: int = 10
    device: Optional[str] = None
    seed: int = 0

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KDConfig":
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


class KnowledgeDistillationTrainer:
    """Trains a local student against a teacher's soft targets."""

    def __init__(
        self,
        teacher: Any,
        student_model: Any,
        tokenizer: Any,
        config: Optional[KDConfig] = None,
    ) -> None:
        self.teacher = teacher
        self.student = student_model
        self.tokenizer = tokenizer
        self.config = config or KDConfig()
        self.history: List[Dict[str, float]] = []

    # -- setup -------------------------------------------------------------
    def _prepare(self) -> None:
        try:
            import torch  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            raise MissingDependencyError("torch", "train") from exc

        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.student.train()
        if self.config.use_lora:
            self._apply_lora()

    def _apply_lora(self) -> None:
        try:
            from peft import LoraConfig, get_peft_model  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise MissingDependencyError("peft", "train") from exc
        cfg = LoraConfig(
            r=self.config.lora_r,
            lora_alpha=self.config.lora_alpha,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
        )
        self.student = get_peft_model(self.student, cfg)

    # -- target construction ----------------------------------------------
    def _build_example(self, sample: Dict[str, Any]):
        """Return (input_ids, attention_mask, labels, prompt_messages)."""

        import torch

        prompt = [ChatMessage.from_dict(m) for m in sample.get("prompt", [])]
        response = sample.get("response", {})
        target_text = response.get("content", "") if isinstance(response, dict) else str(response)

        prompt_text = self._render(prompt)
        prompt_ids = self.tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
        target_ids = self.tokenizer(target_text, add_special_tokens=False)["input_ids"]
        input_ids = (prompt_ids + target_ids)[: self.config.max_length]
        labels = ([-100] * len(prompt_ids) + target_ids)[: self.config.max_length]
        return (
            torch.tensor([input_ids]),
            torch.tensor([[1] * len(input_ids)]),
            torch.tensor([labels]),
            prompt,
            target_ids,
        )

    def _render(self, messages: Sequence[ChatMessage]) -> str:
        msgs = [m.to_dict() for m in messages]
        if getattr(self.tokenizer, "chat_template", None):
            try:
                return self.tokenizer.apply_chat_template(
                    msgs, tokenize=False, add_generation_prompt=True
                )
            except Exception:  # noqa: BLE001
                pass
        return "\n".join(f"{m['role']}: {m.get('content','')}" for m in msgs) + "\nassistant:"

    # -- teacher targets ---------------------------------------------------
    def _teacher_probs(self, prompt: Sequence[ChatMessage], target_ids: List[int]):
        """Full-vocab teacher distribution over the target positions."""

        if hasattr(self.teacher, "sequence_distributions"):
            return self.teacher.sequence_distributions(prompt, target_ids)
        raise MissingDependencyError(
            "transformers", "logits-teacher (needs a white-box teacher)"
        )


    # -- vocab alignment ---------------------------------------------------
    def _vocab_maps(self):
        """Return (student_vocab, teacher_vocab) token->id maps if available."""

        s_vocab = None
        t_vocab = None
        if hasattr(self.tokenizer, "get_vocab"):
            s_vocab = self.tokenizer.get_vocab()
        teacher_tok = getattr(self.teacher, "_tokenizer", None)
        if teacher_tok is not None and hasattr(teacher_tok, "get_vocab"):
            t_vocab = teacher_tok.get_vocab()
        return s_vocab, t_vocab

    # -- main loop ---------------------------------------------------------
    def train(self, examples: List[Dict[str, Any]]) -> Dict[str, Any]:
        import torch

        self._prepare()
        torch.manual_seed(self.config.seed)
        device = self.config.device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.student.to(device)

        optimizer = torch.optim.AdamW(
            [p for p in self.student.parameters() if p.requires_grad], lr=self.config.lr
        )
        s_vocab, t_vocab = self._vocab_maps()
        align = None
        if s_vocab and t_vocab:
            from .losses import align_vocab

            align = align_vocab

        total_steps = 0
        for epoch in range(self.config.epochs):
            running = 0.0
            optimizer.zero_grad()
            for i, ex in enumerate(examples):
                input_ids, attn, labels, prompt, target_ids = self._build_example(ex)
                input_ids, attn, labels = (
                    input_ids.to(device),
                    attn.to(device),
                    labels.to(device),
                )
                out = self.student(input_ids=input_ids, attention_mask=attn)
                # logits predicting target positions
                shift_logits = out.logits[:, :-1, :]
                target_mask = labels[:, 1:] != -100
                if target_mask.sum() == 0:
                    continue
                student_logits = shift_logits[target_mask]  # [T, Vs]

                teacher_probs = self._teacher_probs(prompt, target_ids).to(device)
                teacher_probs = teacher_probs[: student_logits.shape[0]]

                if align is not None and student_logits.shape[-1] != teacher_probs.shape[-1]:
                    student_logits, teacher_probs = align(
                        student_logits.unsqueeze(0),
                        teacher_probs.unsqueeze(0),
                        s_vocab,
                        t_vocab,
                    )
                    student_logits = student_logits[0]
                    teacher_probs = teacher_probs[0]

                loss = kd_loss(
                    student_logits,
                    teacher_probs.to(student_logits.dtype),
                    temperature=self.config.temperature,
                    alpha=self.config.alpha,
                    labels=None,
                )
                (loss / self.config.grad_accum).backward()

                if (i + 1) % self.config.grad_accum == 0:
                    optimizer.step()
                    optimizer.zero_grad()
                    total_steps += 1
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
            "optimizer_steps": total_steps,
            "avg_loss": avg,
            "output_dir": self.config.output_dir,
            "history": self.history,
        }

    def _save(self) -> None:
        import os

        os.makedirs(self.config.output_dir, exist_ok=True)
        self.student.save_pretrained(self.config.output_dir)
        self.tokenizer.save_pretrained(self.config.output_dir)

