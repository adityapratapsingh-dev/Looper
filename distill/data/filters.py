"""Composable quality filters for synthetic/distilled samples.

Filters are registered by name so a config can request them:

    filters:
      - name: length
        min_chars: 8
        max_chars: 4000
      - name: banned_substrings
        substrings: ["as an ai language model", "i cannot"]

``FilterChain`` runs them in order, short-circuits on the first rejection and
records per-filter statistics.
"""

from __future__ import annotations

import abc
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..registry import FILTERS
from .schema import Sample

__all__ = [
    "Filter",
    "FilterResult",
    "FilterChain",
    "LengthFilter",
    "BannedSubstringsFilter",
    "RequiredSubstringsFilter",
    "RegexFilter",
    "RepetitionFilter",
    "NonEmptyResponseFilter",
]


@dataclass
class FilterResult:
    keep: bool
    reason: str = ""
    filter: str = ""
    score: Optional[float] = None


class Filter(abc.ABC):
    """Base class for sample filters."""

    name = "filter"

    def keep(self, sample: Sample) -> bool:  # pragma: no cover - overridden
        raise NotImplementedError

    def apply(self, sample: Sample) -> FilterResult:
        ok = self.keep(sample)
        return FilterResult(keep=ok, filter=self.name, reason="" if ok else "rejected")


def register_filter(name: str):
    def deco(cls):
        FILTERS.add(name, cls)
        cls.name = name
        return cls

    return deco


@register_filter("non_empty")
class NonEmptyResponseFilter(Filter):
    """Drop empty or whitespace-only responses."""

    min_chars = 1

    def __init__(self, min_chars: int = 1) -> None:
        self.min_chars = min_chars

    def keep(self, sample: Sample) -> bool:
        return len(sample.completion.strip()) >= self.min_chars


@register_filter("length")
class LengthFilter(Filter):
    def __init__(self, min_chars: int = 1, max_chars: Optional[int] = None) -> None:
        self.min_chars = min_chars
        self.max_chars = max_chars

    def keep(self, sample: Sample) -> bool:
        n = len(sample.completion)
        if n < self.min_chars:
            return False
        if self.max_chars is not None and n > self.max_chars:
            return False
        return True


@register_filter("banned_substrings")
class BannedSubstringsFilter(Filter):
    def __init__(self, substrings: Optional[List[str]] = None, case_sensitive: bool = False) -> None:
        self.substrings = substrings or []
        self.case_sensitive = case_sensitive

    def keep(self, sample: Sample) -> bool:
        text = sample.completion
        if not self.case_sensitive:
            text = text.lower()
        for s in self.substrings:
            needle = s if self.case_sensitive else s.lower()
            if needle in text:
                return False
        return True


@register_filter("required_substrings")
class RequiredSubstringsFilter(Filter):
    def __init__(self, substrings: Optional[List[str]] = None, mode: str = "any") -> None:
        self.substrings = substrings or []
        self.mode = mode  # "any" or "all"

    def keep(self, sample: Sample) -> bool:
        text = sample.completion.lower()
        hits = [s.lower() in text for s in self.substrings]
        if not hits:
            return True
        return any(hits) if self.mode == "any" else all(hits)


@register_filter("regex")
class RegexFilter(Filter):
    def __init__(self, pattern: str = "", must_match: bool = True, flags: int = 0) -> None:
        self.regex = re.compile(pattern, flags)
        self.must_match = must_match

    def keep(self, sample: Sample) -> bool:
        found = bool(self.regex.search(sample.completion))
        return found if self.must_match else not found


@register_filter("repetition")
class RepetitionFilter(Filter):
    """Reject responses with excessive repeated n-grams (a common LLM failure)."""

    def __init__(self, n: int = 8, max_repeats: int = 3) -> None:
        self.n = n
        self.max_repeats = max_repeats

    def keep(self, sample: Sample) -> bool:
        words = sample.completion.split()
        if len(words) < self.n * 2:
            return True
        grams: Dict[tuple, int] = {}
        for i in range(len(words) - self.n + 1):
            g = tuple(words[i : i + self.n])
            grams[g] = grams.get(g, 0) + 1
            if grams[g] > self.max_repeats:
                return False
        return True


@dataclass
class FilterChain:
    """Apply an ordered list of filters, tracking rejection statistics."""

    filters: List[Filter] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)

    def add(self, f: Filter) -> "FilterChain":
        self.filters.append(f)
        return self

    def apply(self, sample: Sample) -> FilterResult:
        for f in self.filters:
            res = f.apply(sample)
            if not res.keep:
                self.stats[res.filter] = self.stats.get(res.filter, 0) + 1
                return res
        return FilterResult(keep=True)

    def filter(self, samples: List[Sample]) -> List[Sample]:
        kept: List[Sample] = []
        for s in samples:
            if self.apply(s).keep:
                kept.append(s)
        return kept

    @classmethod
    def from_config(cls, specs: List[Dict[str, Any]]) -> "FilterChain":
        chain = cls()
        for spec in specs or []:
            spec = dict(spec)
            name = spec.pop("name")
            factory = FILTERS.get(name)
            chain.add(factory(**spec))
        return chain
