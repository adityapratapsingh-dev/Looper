"""Data layer for response/black-box distillation."""

from .dedupe import exact_dedupe, minhash_signature, near_dedupe, normalize_text, shingles
from .filters import (
    BannedSubstringsFilter,
    Filter,
    FilterChain,
    FilterResult,
    LengthFilter,
    NonEmptyResponseFilter,
    RegexFilter,
    RepetitionFilter,
    RequiredSubstringsFilter,
)
from .formatters import (
    format_alpaca,
    format_chat,
    format_sharegpt,
    format_text,
    get_formatter,
    render_conversation,
)
from .schema import Sample

__all__ = [
    "Sample",
    "Filter",
    "FilterChain",
    "FilterResult",
    "NonEmptyResponseFilter",
    "LengthFilter",
    "BannedSubstringsFilter",
    "RequiredSubstringsFilter",
    "RegexFilter",
    "RepetitionFilter",
    "exact_dedupe",
    "near_dedupe",
    "normalize_text",
    "shingles",
    "minhash_signature",
    "format_chat",
    "format_alpaca",
    "format_sharegpt",
    "format_text",
    "get_formatter",
    "render_conversation",
]
