"""Distillation losses.

Pure-Python helpers (``softmax``, ``kl_divergence``, ``js_divergence``) are
always available and are unit-tested without torch. The tensor versions
(``kd_loss``) are imported lazily and mirror the classic Hinton formulation:

    L = alpha * T^2 * KL( softmax(student/T) || softmax(teacher/T) )
        + (1 - alpha) * CE(student, hard_labels)

The ``T^2`` factor keeps gradient magnitudes comparable across temperatures.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "softmax",
    "kl_divergence",
    "js_divergence",
    "temperature_scale",
    "kd_loss",
]

_EPS = 1e-12


# -- pure-python helpers ---------------------------------------------------
def softmax(logits: Sequence[float], temperature: float = 1.0) -> List[float]:
    t = max(temperature, _EPS)
    m = max(logits)
    exps = [math.exp((x - m) / t) for x in logits]
    total = sum(exps) or 1.0
    return [e / total for e in exps]


def temperature_scale(probs: Dict[str, float], temperature: float) -> Dict[str, float]:
    """Re-softmax a probability distribution (log-domain) at a new temperature."""

    if temperature == 1.0:
        return dict(probs)
    logs = {k: math.log(max(v, _EPS)) / max(temperature, _EPS) for k, v in probs.items()}
    m = max(logs.values())
    exps = {k: math.exp(v - m) for k, v in logs.items()}
    total = sum(exps.values()) or 1.0
    return {k: v / total for k, v in exps.items()}


def kl_divergence(p: Sequence[float], q: Sequence[float]) -> float:
    """KL(p || q) for aligned discrete distributions."""

    total = 0.0
    for pi, qi in zip(p, q):
        if pi > 0:
            total += pi * math.log(pi / max(qi, _EPS))
    return total


def js_divergence(p: Sequence[float], q: Sequence[float]) -> float:
    """Symmetric Jensen-Shannon divergence (a bounded similarity measure)."""

    m = [(pi + qi) / 2.0 for pi, qi in zip(p, q)]
    return 0.5 * kl_divergence(p, m) + 0.5 * kl_divergence(q, m)


# -- torch loss ------------------------------------------------------------
def kd_loss(
    student_logits,
    teacher_probs,
    *,
    temperature: float = 2.0,
    alpha: float = 0.9,
    labels=None,
    ignore_index: int = -100,
    reduction: str = "mean",
):
    """Classic knowledge-distillation loss (requires torch).

    Parameters
    ----------
    student_logits : Tensor[B, V]
    teacher_probs  : Tensor[B, V] soft targets (already softmax-ed, summed to 1)
    labels         : optional Tensor[B] hard targets for the CE term
    """

    import torch
    import torch.nn.functional as F

    log_student = F.log_softmax(student_logits / temperature, dim=-1)
    # KL(teacher || student) with soft targets; batchmean over the vocab dim.
    soft = F.kl_div(log_student, teacher_probs, reduction="batchmean")
    soft = soft * (temperature**2)

    if labels is None or alpha >= 1.0:
        return soft if reduction == "mean" else soft * student_logits.shape[0]

    hard = F.cross_entropy(
        student_logits, labels, ignore_index=ignore_index, reduction=reduction
    )
    if reduction == "mean":
        return alpha * soft + (1.0 - alpha) * hard
    return alpha * soft * student_logits.shape[0] + (1.0 - alpha) * hard


def align_vocab(
    student_logits,
    teacher_probs,
    student_vocab: Dict[str, int],
    teacher_vocab: Dict[str, int],
    min_prob: float = 0.0,
) -> Tuple["object", "object"]:
    """Re-index teacher probabilities onto the student vocabulary (requires torch).

    Only tokens present in both vocabularies are kept; a shared sub-token
    vocabulary (e.g. same tokenizer family) makes this the identity map.
    """

    import torch

    shared = [
        (student_vocab[tok], teacher_vocab[tok])
        for tok in student_vocab
        if tok in teacher_vocab
    ]
    if not shared:
        raise ValueError("student and teacher vocabularies have no tokens in common")
    s_idx = torch.tensor([s for s, _ in shared], dtype=torch.long)
    t_idx = torch.tensor([t for _, t in shared], dtype=torch.long)

    aligned_student = student_logits[..., s_idx]
    aligned_teacher = teacher_probs[..., t_idx]
    # Renormalise the teacher over the shared support.
    aligned_teacher = aligned_teacher / aligned_teacher.sum(dim=-1, keepdim=True).clamp_min(_EPS)
    return aligned_student, aligned_teacher
