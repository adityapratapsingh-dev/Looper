"""Evaluation: metrics and teacher/student comparison harness."""

from .harness import EvalResult, Evaluator
from .metrics import (
    aggregate,
    distinct_n,
    distribution_metrics,
    exact_match,
    levenshtein,
    normalized_edit_similarity,
    token_f1,
)

__all__ = [
    "Evaluator",
    "EvalResult",
    "exact_match",
    "token_f1",
    "levenshtein",
    "normalized_edit_similarity",
    "distinct_n",
    "distribution_metrics",
    "aggregate",
]
