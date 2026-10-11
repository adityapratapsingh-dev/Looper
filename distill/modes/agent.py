"""Agent distillation: capture teacher-agent trajectories and convert to data.

The teacher agent is run over a set of tasks with a tool set; every episode is
recorded as a :class:`~distill.types.Trajectory`, optionally scored/verified,
filtered, and exported either as per-step behaviour-cloning examples or as whole
conversations for SFT.

Config keys
-----------
teacher      : provider spec
tasks        : list[str] OR tasks_file: path
tools        : list of built-in tool names, or "default" (calculator, word_count,
               knowledge_search)
system_prompt: optional system message
max_steps    : agent loop budget (default 6)
sampling     : SamplingParams dict
verifier     : {"type": "contains", "value": "..."} -> sets success + reward
filter       : {"min_reward": float, "succeeded_only": bool, "max_steps": int}
format       : bc | conversations   (default: bc)
output       : path to write trajectory JSONL
export       : path to write the training-ready examples JSONL
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..agent import (
    AgentRunner,
    RunConfig,
    TrajectoryDataset,
    behavior_cloning_examples,
    filter_trajectories,
    trajectory_to_conversation,
    write_jsonl,
)
from ..agent.tools import default_registry
from ..agent.tools import FunctionTool  # noqa: F401 - re-exported for custom use
from ..providers.factory import build_provider
from ..types import Role, SamplingParams, Trajectory
from .base import Mode, ModeResult, register_mode

__all__ = ["AgentDistillationMode"]


def _make_verifier(spec: Optional[Dict[str, Any]]) -> Optional[Callable[[Trajectory], bool]]:
    if not spec:
        return None
    kind = spec.get("type", "contains")
    value = spec.get("value", "")
    case_sensitive = bool(spec.get("case_sensitive", False))

    def verify(traj: Trajectory) -> bool:
        finals = [m.content for m in traj.messages if m.role == Role.ASSISTANT and not m.has_tool_calls]
        text = finals[-1] if finals else ""
        if not case_sensitive:
            text = text.lower()
            needle = str(value).lower()
        else:
            needle = str(value)
        if kind == "contains":
            return needle in text
        if kind == "equals":
            return text.strip() == needle.strip()
        if kind == "regex":
            import re

            return bool(re.search(str(value), text, 0 if case_sensitive else re.IGNORECASE))
        return False

    return verify


@register_mode("agent")
class AgentDistillationMode(Mode):
    name = "agent"

    def run(self) -> ModeResult:
        cfg = self.config
        teacher = build_provider(cfg.get("teacher"), default="echo")
        tasks = self._load_tasks(cfg)

        registry = self._build_registry(cfg.get("tools", "default"))
        run_cfg = RunConfig(
            max_steps=int(cfg.get("max_steps", 6)),
            system_prompt=cfg.get("system_prompt"),
            params=SamplingParams.from_dict(cfg.get("sampling", {}) or {}),
        )
        verifier = _make_verifier(cfg.get("verifier"))
        reward_fn = (
            (lambda t: 1.0 if t.success else 0.0) if verifier else None
        )

        runner = AgentRunner(
            teacher, registry, config=run_cfg, reward_fn=reward_fn, verify_fn=verifier
        )
        trajectories: List[Trajectory] = runner.run_many(tasks)

        stats: Dict[str, Any] = {"num_tasks": len(tasks)}
        dataset = TrajectoryDataset(trajectories)
        stats.update(dataset.stats())

        fcfg = cfg.get("filter", {}) or {}
        kept = filter_trajectories(
            trajectories,
            min_reward=fcfg.get("min_reward"),
            succeeded_only=bool(fcfg.get("succeeded_only", False)),
            max_steps=fcfg.get("max_steps"),
        )
        stats["after_filter"] = len(kept)
        kept_ds = TrajectoryDataset(kept)

        fmt = cfg.get("format", "bc")
        if fmt == "conversations":
            examples = kept_ds.to_conversations()
        else:
            examples = kept_ds.to_bc_examples()

        output = cfg.get("output")
        if output:
            kept_ds.save(output)
        export = cfg.get("export")
        if export:
            write_jsonl(export, examples)

        stats["format"] = fmt
        stats["teacher"] = f"{teacher.name}:{teacher.model}"
        stats["tools"] = registry.names()
        return ModeResult(
            mode=self.name,
            output_path=export or output,
            num_examples=len(examples),
            stats=stats,
        )

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _load_tasks(cfg: Dict[str, Any]) -> List[str]:
        tasks: List[str] = list(cfg.get("tasks", []) or [])
        tasks_file: Optional[str] = cfg.get("tasks_file")
        if tasks_file:
            text = Path(tasks_file).read_text(encoding="utf-8")
            tasks.extend(
                line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")
            )
        if not tasks:
            raise ValueError("agent mode requires 'tasks' or 'tasks_file'")
        return tasks

    @staticmethod
    def _build_registry(spec: Any):
        if spec in (None, "default", []):
            return default_registry()
        if spec == "none":
            from ..agent.tools import ToolRegistry

            return ToolRegistry()
        base = default_registry()
        if isinstance(spec, list):
            names = [str(s) for s in spec]
            filtered = default_registry()
            keep = set(names)
            filtered._tools = {k: v for k, v in base._tools.items() if k in keep}  # noqa: SLF001
            return filtered
        return base
