"""Trajectory → training-data conversion and JSONL persistence.

Agent distillation has two common shapes:

* **Behavior cloning** — turn each assistant turn into a supervised target
  conditioned on the preceding context (:func:`behavior_cloning_examples`).
* **Full-episode SFT** — keep the whole transcript as one training example with
  assistant spans as targets (:func:`trajectory_to_conversation`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from ..types import ChatMessage, Role, Trajectory

__all__ = [
    "TrajectoryDataset",
    "behavior_cloning_examples",
    "trajectory_to_conversation",
    "filter_trajectories",
    "write_jsonl",
    "read_jsonl",
]


def behavior_cloning_examples(traj: Trajectory) -> List[Dict[str, Any]]:
    """Yield one example per assistant turn: {context, target, tools}.

    The context is everything up to (but excluding) the assistant turn, so a
    student trained on these examples learns the teacher's policy action-by-action.
    """

    examples: List[Dict[str, Any]] = []
    context: List[ChatMessage] = []
    for msg in traj.messages:
        if msg.role == Role.ASSISTANT:
            examples.append(
                {
                    "trajectory_id": traj.id,
                    "task": traj.task,
                    "messages": [m.to_dict() for m in context],
                    "target": msg.to_dict(),
                    "tools": [t.to_dict() for t in traj.tools],
                    "reward": traj.reward,
                }
            )
        context.append(msg)
    return examples


def trajectory_to_conversation(traj: Trajectory, include_tools: bool = True) -> Dict[str, Any]:
    """Whole-episode example with assistant spans to be trained on."""

    return {
        "trajectory_id": traj.id,
        "task": traj.task,
        "messages": [m.to_dict() for m in traj.messages],
        "tools": [t.to_dict() for t in traj.tools] if include_tools else [],
        "reward": traj.reward,
        "success": traj.success,
        "num_steps": traj.num_steps,
    }


def filter_trajectories(
    trajs: Iterable[Trajectory],
    *,
    min_reward: Optional[float] = None,
    succeeded_only: bool = False,
    max_steps: Optional[int] = None,
) -> List[Trajectory]:
    out: List[Trajectory] = []
    for t in trajs:
        if min_reward is not None and (t.reward is None or t.reward < min_reward):
            continue
        if succeeded_only and not t.success:
            continue
        if max_steps is not None and t.num_steps > max_steps:
            continue
        out.append(t)
    return out


@dataclass
class TrajectoryDataset:
    """In-memory collection of trajectories with convenience converters."""

    trajectories: List[Trajectory] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.trajectories)

    def __iter__(self) -> Iterator[Trajectory]:
        return iter(self.trajectories)

    def to_bc_examples(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for t in self.trajectories:
            out.extend(behavior_cloning_examples(t))
        return out

    def to_conversations(self) -> List[Dict[str, Any]]:
        return [trajectory_to_conversation(t) for t in self.trajectories]

    def stats(self) -> Dict[str, Any]:
        n = len(self.trajectories)
        steps = [t.num_steps for t in self.trajectories]
        rewards = [t.reward for t in self.trajectories if t.reward is not None]
        successes = [t.success for t in self.trajectories if t.success is not None]
        return {
            "num_trajectories": n,
            "avg_steps": (sum(steps) / n) if n else 0.0,
            "total_steps": sum(steps),
            "avg_reward": (sum(rewards) / len(rewards)) if rewards else None,
            "success_rate": (sum(1 for s in successes if s) / len(successes))
            if successes
            else None,
        }

    @classmethod
    def load(cls, path: str | Path) -> "TrajectoryDataset":
        return cls([Trajectory.from_dict(d) for d in read_jsonl(path)])

    def save(self, path: str | Path) -> None:
        write_jsonl(path, (t.to_dict() for t in self.trajectories))


# -- JSONL helpers ---------------------------------------------------------
def write_jsonl(path: str | Path, records: Iterable[Dict[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += 1
    return count


def read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    p = Path(path)
    records: List[Dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
