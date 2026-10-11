"""Mode base class and result type."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Type

from ..registry import MODES

__all__ = ["Mode", "ModeResult", "get_mode", "register_mode"]


@dataclass
class ModeResult:
    """Summary returned by every mode's ``run``."""

    mode: str
    output_path: Optional[str] = None
    num_examples: int = 0
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "output_path": self.output_path,
            "num_examples": self.num_examples,
            "stats": self.stats,
        }


class Mode(abc.ABC):
    """A distillation mode: given a config, produce artifacts + a summary."""

    name = "mode"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}

    @abc.abstractmethod
    def run(self) -> ModeResult:
        """Execute the mode and return a :class:`ModeResult`."""

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<{type(self).__name__} name={self.name!r}>"


def register_mode(name: str):
    def deco(cls: Type[Mode]) -> Type[Mode]:
        cls.name = name
        MODES.add(name, cls)
        return cls

    return deco


def get_mode(name: str) -> Type[Mode]:
    return MODES.get(name)
