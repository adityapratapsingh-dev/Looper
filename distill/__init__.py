"""distill — a pluggable distillation framework for LLMs and AI agents.

Three first-class distillation modes share one provider/registry backbone:

* ``data``   — black-box response distillation: a teacher generates synthetic
  data/trajectories that are filtered, deduped and formatted for fine-tuning.
* ``logits`` — white-box knowledge distillation: a student is trained to match
  the teacher's temperature-scaled token distribution (plus optional hard-label
  cross-entropy).
* ``agent``  — agent distillation: full agent trajectories (tool calls, tool
  results, reasoning) are captured from a strong teacher agent and distilled
  into a cheaper student policy.

See ``docs/architecture.md`` for the full design and ``examples/`` for runnable
quickstarts.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .types import (
    ChatMessage,
    Completion,
    Role,
    SamplingParams,
    TokenLogprob,
    ToolCall,
    ToolSpec,
    Trajectory,
    Usage,
)

__all__ = [
    "__version__",
    "ChatMessage",
    "Completion",
    "Role",
    "SamplingParams",
    "TokenLogprob",
    "ToolCall",
    "ToolSpec",
    "Trajectory",
    "Usage",
]
