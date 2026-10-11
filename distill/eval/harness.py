"""Comparison harness: teacher vs student, for text and agent tasks.

Two evaluations:

* :meth:`Evaluator.evaluate_prompts` — generate teacher and student responses to
  the same prompts and score agreement (exact match, token-F1, edit similarity).
* :meth:`Evaluator.evaluate_agents` — run both as agents over tasks and compare
  success rate and average steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..agent.runner import AgentRunner, RunConfig
from ..agent.tools import ToolRegistry
from ..types import ChatMessage, SamplingParams
from .metrics import (
    aggregate,
    distinct_n,
    exact_match,
    normalized_edit_similarity,
    token_f1,
)

__all__ = ["Evaluator", "EvalResult"]


@dataclass
class EvalResult:
    metrics: Dict[str, float] = field(default_factory=dict)
    rows: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"metrics": self.metrics, "num_rows": len(self.rows)}


class Evaluator:
    def __init__(
        self,
        teacher: Any,
        student: Any,
        *,
        params: Optional[SamplingParams] = None,
    ) -> None:
        self.teacher = teacher
        self.student = student
        self.params = params or SamplingParams(temperature=0.0, max_tokens=256)

    # -- text --------------------------------------------------------------
    def evaluate_prompts(
        self, prompts: List[str], system_prompt: Optional[str] = None
    ) -> EvalResult:
        rows: List[Dict[str, Any]] = []
        teacher_texts: List[str] = []
        student_texts: List[str] = []
        for prompt in prompts:
            messages: List[ChatMessage] = []
            if system_prompt:
                messages.append(ChatMessage.system(system_prompt))
            messages.append(ChatMessage.user(prompt))

            t = self.teacher.chat(messages, params=self.params)
            s = self.student.chat(messages, params=self.params)
            t_text, s_text = t.text, s.text
            teacher_texts.append(t_text)
            student_texts.append(s_text)
            rows.append(
                {
                    "prompt": prompt,
                    "teacher": t_text,
                    "student": s_text,
                    "exact_match": exact_match(s_text, t_text),
                    "token_f1": token_f1(s_text, t_text),
                    "edit_similarity": normalized_edit_similarity(s_text, t_text),
                }
            )
        metrics = aggregate(
            [{k: v for k, v in r.items() if isinstance(v, float)} for r in rows]
        )
        metrics["student_distinct_2"] = distinct_n(student_texts, 2)
        metrics["teacher_distinct_2"] = distinct_n(teacher_texts, 2)
        return EvalResult(metrics=metrics, rows=rows)

    # -- agents ------------------------------------------------------------
    def evaluate_agents(
        self,
        tasks: List[str],
        tools: ToolRegistry,
        *,
        run_config: Optional[RunConfig] = None,
        reward_fn: Optional[Any] = None,
        verify_fn: Optional[Any] = None,
    ) -> EvalResult:
        cfg = run_config or RunConfig(max_steps=6, params=self.params)
        teacher_runner = AgentRunner(
            self.teacher, tools, config=cfg, reward_fn=reward_fn, verify_fn=verify_fn
        )
        student_runner = AgentRunner(
            self.student, tools, config=cfg, reward_fn=reward_fn, verify_fn=verify_fn
        )
        rows: List[Dict[str, Any]] = []
        for task in tasks:
            t_traj = teacher_runner.run(task)
            s_traj = student_runner.run(task)
            rows.append(
                {
                    "task": task,
                    "teacher_success": bool(t_traj.success),
                    "student_success": bool(s_traj.success),
                    "teacher_steps": t_traj.num_steps,
                    "student_steps": s_traj.num_steps,
                }
            )

        def mean(key: str) -> float:
            return (sum(1.0 for r in rows if r[key]) / len(rows)) if rows else 0.0

        metrics = {
            "teacher_success_rate": mean("teacher_success"),
            "student_success_rate": mean("student_success"),
            "avg_teacher_steps": (
                sum(r["teacher_steps"] for r in rows) / len(rows) if rows else 0.0
            ),
            "avg_student_steps": (
                sum(r["student_steps"] for r in rows) / len(rows) if rows else 0.0
            ),
        }
        metrics["success_gap"] = (
            metrics["teacher_success_rate"] - metrics["student_success_rate"]
        )
        return EvalResult(metrics=metrics, rows=rows)
