"""Training layer: KD and SFT trainers plus distillation losses."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .kd import KDConfig, KnowledgeDistillationTrainer
from .losses import js_divergence, kd_loss, kl_divergence, softmax, temperature_scale
from .sft import SFTConfig, SupervisedFineTuneTrainer, split_messages

__all__ = [
    "KDConfig",
    "KnowledgeDistillationTrainer",
    "SFTConfig",
    "SupervisedFineTuneTrainer",
    "split_messages",
    "kd_loss",
    "kl_divergence",
    "js_divergence",
    "softmax",
    "temperature_scale",
    "load_student_model",
]


def load_student_model(
    spec: Dict[str, Any],
) -> Tuple[Any, Any]:
    """Load a student (model, tokenizer) from a config dict.

    ``spec`` keys: ``model`` (HF id or path), ``device``, ``dtype``,
    ``load_in_4bit``, ``trust_remote_code``.
    """

    from ..errors import MissingDependencyError

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise MissingDependencyError("transformers", "train") from exc

    model_id = spec.get("model") or spec.get("model_id")
    if not model_id:
        raise ValueError("student spec requires a 'model'")
    tokenizer = AutoTokenizer.from_pretrained(
        model_id, trust_remote_code=bool(spec.get("trust_remote_code", False))
    )
    kwargs: Dict[str, Any] = {
        "trust_remote_code": bool(spec.get("trust_remote_code", False)),
        "device_map": spec.get("device") or "auto",
    }
    if spec.get("dtype") and spec["dtype"] != "auto":
        kwargs["torch_dtype"] = spec["dtype"]
    if spec.get("load_in_4bit"):
        try:
            from transformers import BitsAndBytesConfig  # type: ignore

            kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True)
        except Exception:  # noqa: BLE001
            pass
    model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    return model, tokenizer
