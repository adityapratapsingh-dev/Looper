"""Distillation modes: ``data``, ``logits`` and ``agent``.

Each mode is a small orchestrator that reads a config dict and returns a run
summary. Modes are registered so they can be selected by name from a config file
or the CLI.
"""

from __future__ import annotations

from .base import Mode, ModeResult, get_mode
from .data import DataDistillationMode
from .agent import AgentDistillationMode
from .logits import LogitsDistillationMode

__all__ = [
    "Mode",
    "ModeResult",
    "get_mode",
    "DataDistillationMode",
    "AgentDistillationMode",
    "LogitsDistillationMode",
]
