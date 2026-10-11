"""A minimal, serialisable sample type used by the data-distillation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..types import ChatMessage, TokenLogprob, new_id

__all__ = ["Sample"]


@dataclass
class Sample:
    """One (prompt -> response) distillation example.

    ``prompt`` is the full context; ``response`` is the teacher's target turn.
    ``score`` and ``metadata`` carry filter/judge results. ``teacher_logprobs``
    captures teacher distributions when the teacher exposes them.
    """

    prompt: List[ChatMessage] = field(default_factory=list)
    response: ChatMessage = field(default_factory=ChatMessage.assistant)
    id: str = field(default_factory=lambda: new_id("smp_"))
    source: str = ""
    score: Optional[float] = None
    teacher_logprobs: List[TokenLogprob] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "prompt": [m.to_dict() for m in self.prompt],
            "response": self.response.to_dict(),
            "source": self.source,
            "score": self.score,
            "teacher_logprobs": [t.to_dict() for t in self.teacher_logprobs],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Sample":
        return cls(
            prompt=[ChatMessage.from_dict(m) for m in d.get("prompt", [])],
            response=ChatMessage.from_dict(d["response"])
            if d.get("response")
            else ChatMessage.assistant(d.get("completion", "")),
            id=d.get("id") or new_id("smp_"),
            source=d.get("source", ""),
            score=d.get("score"),
            teacher_logprobs=[
                TokenLogprob.from_dict(t) for t in d.get("teacher_logprobs", [])
            ],
            metadata=d.get("metadata", {}) or {},
        )

    @property
    def completion(self) -> str:
        return self.response.content
