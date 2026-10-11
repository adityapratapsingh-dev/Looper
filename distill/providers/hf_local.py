"""Local HuggingFace provider with white-box access to logits.

This is the provider you want for **loss-level** knowledge distillation: it can
return the full next-token distribution (or a full sequence of them) so a student
can be trained against the teacher's soft targets.

Supports LoRA adapters (``adapter_path``) so a distilled student checkpoint can
also serve as a provider for evaluation loops. Everything heavy is imported
lazily.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ..errors import MissingDependencyError, ProviderError
from ..types import ChatMessage, Completion, SamplingParams, Usage
from .base import Provider, ProviderCapabilities, register_provider


@register_provider("hf")
class HuggingFaceProvider(Provider):
    """Local transformers model (teacher or student)."""

    name = "hf"

    def __init__(
        self,
        model: str,
        *,
        device: Optional[str] = None,
        dtype: str = "auto",
        adapter_path: Optional[str] = None,
        trust_remote_code: bool = False,
        load_in_4bit: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model,
            capabilities=ProviderCapabilities(
                tools=True, logprobs=True, white_box=True, async_native=False
            ),
            **kwargs,
        )
        self.device = device
        self.dtype = dtype
        self.adapter_path = adapter_path
        self.trust_remote_code = trust_remote_code
        self.load_in_4bit = load_in_4bit
        self._model = None
        self._tokenizer = None

    # -- loading -----------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            import torch  # noqa: F401
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise MissingDependencyError("transformers", "hf") from exc

        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model, trust_remote_code=self.trust_remote_code
        )
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        load_kwargs: Dict[str, Any] = {
            "trust_remote_code": self.trust_remote_code,
            "device_map": self.device or "auto",
        }
        if self.dtype != "auto":
            load_kwargs["torch_dtype"] = self.dtype
        if self.load_in_4bit:
            try:
                from transformers import BitsAndBytesConfig  # type: ignore

                load_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True)
            except Exception:  # noqa: BLE001
                pass
        self._model = AutoModelForCausalLM.from_pretrained(self.model, **load_kwargs)
        if self.adapter_path:
            try:
                from peft import PeftModel  # type: ignore

                self._model = PeftModel.from_pretrained(self._model, self.adapter_path)
            except Exception as exc:  # noqa: BLE001
                raise MissingDependencyError("peft", "train") from exc
        self._model.eval()

    def _render(self, messages: Sequence[ChatMessage], tools: Optional[Sequence[ToolSpec]] = None) -> str:
        self._ensure_loaded()
        msgs = [m.to_dict() for m in messages]
        tok = self._tokenizer
        if getattr(tok, "chat_template", None):
            try:
                return tok.apply_chat_template(
                    msgs, tokenize=False, add_generation_prompt=True
                )
            except Exception:  # noqa: BLE001 - fall back to a plain format
                pass
        return "\n".join(f"{m['role']}: {m.get('content', '')}" for m in msgs) + "\nassistant:"


    def _encode(self, text: str):
        import torch  # noqa: F401

        return self._tokenizer(text, return_tensors="pt")

    def _chat_once(
        self,
        messages: List[ChatMessage],
        *,
        tools: Optional[Sequence[ToolSpec]],
        params: SamplingParams,
        **kwargs: Any,
    ) -> Completion:
        import time

        import torch

        self._ensure_loaded()
        prompt = self._render(messages, tools)
        enc = self._encode(prompt)
        input_ids = enc["input_ids"].to(self._model.device)
        attention_mask = enc.get("attention_mask")
        if attention_mask is not None:
            attention_mask = attention_mask.to(self._model.device)

        gen_kwargs: Dict[str, Any] = {
            "max_new_tokens": params.max_tokens,
            "do_sample": params.temperature > 0,
            "temperature": max(params.temperature, 1e-5),
            "top_p": params.top_p,
            "pad_token_id": self._tokenizer.pad_token_id,
        }
        if params.top_k:
            gen_kwargs["top_k"] = params.top_k
        if params.stop:
            gen_kwargs["stop_strings"] = params.stop
        if params.seed is not None:
            torch.manual_seed(params.seed)

        start = time.perf_counter()
        with torch.no_grad():
            out = self._model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                tokenizer=self._tokenizer,
                **{k: v for k, v in gen_kwargs.items() if v is not None},
            )
        new_tokens = out[0][input_ids.shape[-1]:]
        text = self._tokenizer.decode(new_tokens, skip_special_tokens=True)
        usage = Usage(
            prompt_tokens=int(input_ids.shape[-1]),
            completion_tokens=int(new_tokens.shape[-1]),
        )
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        return Completion(
            text=text,
            finish_reason="stop",
            usage=usage,
            model=self.model,
            provider=self.name,
            latency_ms=(time.perf_counter() - start) * 1000.0,
        )

    # -- white-box hooks ---------------------------------------------------
    def next_token_distribution(
        self, messages: Sequence[ChatMessage], top_k: int = 128, **kwargs: Any
    ) -> Dict[str, float]:
        """Top-k softmax distribution over the vocabulary for the next token."""

        return dict(self.next_token_probs(messages, top_k=top_k))

    def next_token_probs(
        self, messages: Sequence[ChatMessage], top_k: int = 50
    ) -> List[tuple[str, float]]:
        """Top-k (token, prob) pairs for the next token."""

        import torch

        self._ensure_loaded()
        enc = self._encode(self._render(messages))
        input_ids = enc["input_ids"].to(self._model.device)
        with torch.no_grad():
            logits = self._model(input_ids=input_ids).logits[0, -1, :].float()
        probs = torch.softmax(logits, dim=-1)
        top = torch.topk(probs, k=min(top_k, probs.shape[-1]))
        return [
            (self._tokenizer.decode([int(i)]), float(p))
            for i, p in zip(top.indices.tolist(), top.values.tolist())
        ]

    def sequence_distributions(
        self, messages: Sequence[ChatMessage], target_token_ids: Sequence[int]
    ):
        """Teacher distribution at each position for a target token sequence.

        Returns a tensor of shape ``[T, V]`` (temperature-1 softmax over vocab)
        aligned to ``target_token_ids``. Used by the logits-KD trainer.
        """

        import torch
        import torch.nn.functional as F

        self._ensure_loaded()
        prompt_ids = self._tokenizer(self._render(messages), return_tensors="pt")[
            "input_ids"
        ].to(self._model.device)
        full = torch.cat(
            [prompt_ids, torch.tensor([list(target_token_ids)], device=self._model.device)],
            dim=1,
        )
        with torch.no_grad():
            logits = self._model(input_ids=full).logits[0]
        start = prompt_ids.shape[-1] - 1
        teacher_logits = logits[start : start + len(target_token_ids)]
        return F.softmax(teacher_logits.float(), dim=-1)


__all__ = ["HuggingFaceProvider"]

