"""Exact and near-duplicate removal for distilled datasets.

Synthetic data from a teacher is often highly redundant. We provide:

* :func:`exact_dedupe` — normalised-text hashing.
* :func:`minhash_signature` / :func:`near_dedupe` — locality-sensitive MinHash so
  near-identical generations collapse to one representative.
"""

from __future__ import annotations

import hashlib
import re
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .schema import Sample

__all__ = [
    "normalize_text",
    "exact_dedupe",
    "shingles",
    "minhash_signature",
    "near_dedupe",
]

_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    return _WS.sub(" ", text.strip().lower())


def _key_of_factory(key: Optional[Callable[[Sample], str]]):
    if key is not None:
        return key

    def default(sample: Sample) -> str:
        parts = [m.content for m in sample.prompt] + [sample.completion]
        return normalize_text(" ".join(parts))

    return default


def exact_dedupe(
    samples: Iterable[Sample],
    *,
    key: Optional[Callable[[Sample], str]] = None,
) -> List[Sample]:
    """Keep the first sample for each normalised text key."""

    key_of = _key_of_factory(key)
    seen: set = set()
    out: List[Sample] = []
    for s in samples:
        k = key_of(s)
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def shingles(text: str, k: int = 5) -> List[str]:
    words = normalize_text(text).split()
    if len(words) < k:
        return [" ".join(words)] if words else []
    return [" ".join(words[i : i + k]) for i in range(len(words) - k + 1)]


def _hash(seed: int, value: str) -> int:
    h = hashlib.blake2b(value.encode("utf-8"), digest_size=8, salt=str(seed).encode())
    return int.from_bytes(h.digest(), "big")


def minhash_signature(
    text: str, num_perm: int = 64, k: int = 5
) -> Tuple[int, ...]:
    sh = shingles(text, k)
    if not sh:
        return tuple([0] * num_perm)
    return tuple(min(_hash(i, s) for s in sh) for i in range(num_perm))


def _jaccard(a: Sequence[int], b: Sequence[int]) -> float:
    matches = sum(1 for x, y in zip(a, b) if x == y)
    return matches / len(a) if a else 0.0


def near_dedupe(
    samples: Iterable[Sample],
    *,
    threshold: float = 0.85,
    num_perm: int = 64,
    k: int = 5,
    bands: int = 16,
    key: Optional[Callable[[Sample], str]] = None,
) -> List[Sample]:
    """LSH-banded MinHash de-duplication.

    Samples whose estimated Jaccard similarity to an already-kept sample is
    >= ``threshold`` are dropped.
    """

    key_of = _key_of_factory(key)
    rows = max(1, num_perm // bands)
    buckets: Dict[Tuple[int, Tuple[int, ...]], List[int]] = {}
    kept: List[Sample] = []
    signatures: List[Tuple[int, ...]] = []

    for s in samples:
        text = key_of(s)
        sig = minhash_signature(text, num_perm=num_perm, k=k)
        # Candidate buckets from banding.
        candidates: set = set()
        for b in range(bands):
            band = sig[b * rows : (b + 1) * rows]
            candidates.update(buckets.get((b, band), []))

        duplicate = False
        for idx in candidates:
            if _jaccard(sig, signatures[idx]) >= threshold:
                duplicate = True
                break
        if duplicate:
            continue

        for b in range(bands):
            band = sig[b * rows : (b + 1) * rows]
            buckets.setdefault((b, band), []).append(len(kept))
        kept.append(s)
        signatures.append(sig)

    return kept
