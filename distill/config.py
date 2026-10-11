"""Run configuration: YAML/JSON loading, env interpolation and dispatch.

A config is a plain mapping with a ``mode`` key (``data`` | ``logits`` |
``agent``) and mode-specific keys. Optionally it may contain ``stages`` — a list
of sub-configs executed in order (e.g. generate data, then fine-tune).

    mode: data
    teacher: {provider: echo}
    prompts: ["..."]

String values support ``${ENV_VAR}`` interpolation, and ``api_key_env`` fields are
resolved from the environment at provider-construction time.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .errors import ConfigError
from .modes.base import ModeResult, get_mode

__all__ = ["RunConfig", "load_config", "interpolate_env"]

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def interpolate_env(value: Any) -> Any:
    """Recursively replace ``${VAR}`` with environment values."""

    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate_env(v) for v in value]
    return value


def load_config(path: str | Path) -> Dict[str, Any]:
    """Load a YAML or JSON config file, with env interpolation applied."""

    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config file not found: {p}")
    text = p.read_text(encoding="utf-8")
    if p.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text) or {}
        except ImportError:
            # PyYAML is optional; fall back to the built-in subset parser.
            from . import _yaml

            data = _yaml.loads(text) or {}
    else:
        data = json.loads(text or "{}")
    if not isinstance(data, dict):
        raise ConfigError(f"config root must be a mapping, got {type(data).__name__}")
    return interpolate_env(data)


@dataclass
class RunConfig:
    """A validated, executable run configuration."""

    data: Dict[str, Any] = field(default_factory=dict)
    results: List[ModeResult] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunConfig":
        if not isinstance(data, dict):
            raise ConfigError("run config must be a mapping")
        if "mode" not in data and "stages" not in data:
            raise ConfigError("run config requires a 'mode' or 'stages'")
        return cls(data=interpolate_env(data))

    @classmethod
    def from_file(cls, path: str | Path) -> "RunConfig":
        return cls.from_dict(load_config(path))

    # -- execution ---------------------------------------------------------
    def run(self) -> List[ModeResult]:
        """Execute the config (single mode or an ordered list of stages)."""

        self.results = []
        stages = self.data.get("stages")
        if stages:
            for stage in stages:
                self.results.append(self._run_one(stage))
            return self.results
        self.results.append(self._run_one(self.data))
        return self.results

    @staticmethod
    def _run_one(spec: Dict[str, Any]) -> ModeResult:
        mode_name = spec.get("mode")
        if not mode_name:
            raise ConfigError("each stage requires a 'mode'")
        mode_cls = get_mode(mode_name)
        return mode_cls(spec).run()

    def summary(self) -> Dict[str, Any]:
        return {"stages": [r.to_dict() for r in self.results]}
