"""Evaluation metrics for distillation quality (pure Python, no deps).

Text metrics compare a student's output to the teacher's; distribution metrics
compare probability vectors (e.g. teacher vs student logprobs) via KL/JS.
"""

from __future__ import annotations

import re
from typing import Dict, List, Sequence

from ..train.losses import js_divergence, kl_divergence

__all__ = [
    "exact_match",
    "token_f1",
    "levenshtein",
    "normalized_edit_similarity",
    "distinct_n",
    "distribution_metrics",
    "aggregate",
]

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", (text or "").strip().lower())


def exact_match(prediction: str, reference: str) -> float:
    return 1.0 if _norm(prediction) == _norm(reference) else 0.0


def token_f1(prediction: str, reference: str) -> float:
    p = _norm(prediction).split()
    r = _norm(reference).split()
    if not p and not r:
        return 1.0
    if not p or not r:
        return 0.0
    from collections import Counter

    common = Counter(p) & Counter(r)
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(p)
    recall = overlap / len(r)
    return 2 * precision * recall / (precision + recall)


def levenshtein(a: Sequence[str], b: Sequence[str]) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            substitute = previous[j - 1] + (ca != cb)
            current.append(min(insert, delete, substitute))
        previous = current
    return previous[-1]


def normalized_edit_similarity(prediction: str, reference: str) -> float:
    a, b = _norm(prediction).split(), _norm(reference).split()
    if not a and not b:
        return 1.0
    dist = levenshtein(a, b)
    return 1.0 - dist / max(len(a), len(b), 1)


def distinct_n(texts: Sequence[str], n: int = 2) -> float:
    """Ratio of unique n-grams to total n-grams across ``texts``."""

    total = 0
    unique = set()
    for t in texts:
        toks = _norm(t).split()
        for i in range(len(toks) - n + 1):
            unique.add(tuple(toks[i : i + n]))
            total += 1
    return (len(unique) / total) if total else 0.0


def distribution_metrics(p: Sequence[float], q: Sequence[float]) -> Dict[str, float]:
    """KL/JS divergence and top-1 agreement between two distributions."""

    kl = kl_divergence(p, q)
    js = js_divergence(p, q)
    top1 = 1.0 if (p and q and p.index(max(p)) == q.index(max(q))) else 0.0
    return {"kl": kl, "js": js, "top1_agreement": top1}


def aggregate(rows: List[Dict[str, float]]) -> Dict[str, float]:
    """Mean of each metric across rows."""

    if not rows:
        return {}
    keys = rows[0].keys()
    return {k: sum(r.get(k, 0.0) for r in rows) / len(rows) for k in keys}
