"""The agent loop.

``AgentRunner`` drives a :class:`Provider` with a set of tools, executing tool
calls and feeding results back until the model answers or ``max_steps`` is hit.
The full episode is captured as a :class:`Trajectory`, which is the unit that
agent distillation consumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..types import ChatMessage, Completion, SamplingParams, Trajectory
from .tools import ToolRegistry


@dataclass
class RunConfig:
    max_steps: int = 8
    system_prompt: Optional[str] = None
    params: SamplingParams = field(default_factory=SamplingParams)
    stop_on_tool_error: bool = False
    include_empty_tools: bool = False

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RunConfig":
        d = dict(d or {})
        max_steps = int(d.pop("max_steps", 8))
        system_prompt = d.pop("system_prompt", None)
        params = SamplingParams.from_dict(d.pop("params", {}) or {})
        stop_on_tool_error = bool(d.pop("stop_on_tool_error", False))
        include_empty_tools = bool(d.pop("include_empty_tools", False))
        if d:  # leftover keys fold into params.extra
            params.extra.update(d)
        return cls(
            max_steps=max_steps,
            system_prompt=system_prompt,
            params=params,
            stop_on_tool_error=stop_on_tool_error,
            include_empty_tools=include_empty_tools,
        )


class AgentRunner:
    """Runs a provider as an agent and returns captured trajectories."""

    def __init__(
        self,
        provider: Any,
        tools: Optional[ToolRegistry] = None,
        *,
        config: Optional[RunConfig] = None,
        reward_fn: Optional[Callable[[Trajectory], float]] = None,
        verify_fn: Optional[Callable[[Trajectory], bool]] = None,
    ) -> None:
        self.provider = provider
        self.tools = tools or ToolRegistry()
        self.config = config or RunConfig()
        self.reward_fn = reward_fn
        self.verify_fn = verify_fn

    # -- single episode ----------------------------------------------------
    def run(self, task: str) -> Trajectory:
        specs = self.tools.specs() if len(self.tools) else None
        traj = Trajectory(
            task=task,
            tools=specs or [],
            provider=getattr(self.provider, "name", ""),
            model=getattr(self.provider, "model", ""),
        )

        messages: List[ChatMessage] = []
        if self.config.system_prompt:
            sys_msg = ChatMessage.system(self.config.system_prompt)
            messages.append(sys_msg)
            traj.add(sys_msg)
        user_msg = ChatMessage.user(task)
        messages.append(user_msg)
        traj.add(user_msg)

        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        steps = 0
        for _ in range(self.config.max_steps):
            completion: Completion = self.provider.chat(
                messages, tools=specs, params=self.config.params
            )
            for k in total_usage:
                total_usage[k] += getattr(completion.usage, k, 0)

            assistant = completion.message or ChatMessage.assistant(completion.text)
            messages.append(assistant)
            traj.add(assistant)
            steps += 1

            if not assistant.has_tool_calls:
                break

            for call in assistant.tool_calls:
                result = self.tools.run_to_string(call)
                tool_msg = ChatMessage.tool(result, tool_call_id=call.id, name=call.name)
                messages.append(tool_msg)
                traj.add(tool_msg)
                if self.config.stop_on_tool_error and result.strip().startswith('{"error"'):
                    traj.metadata["stopped_on_tool_error"] = True
                    break
            else:
                continue
            break

        traj.num_steps = steps
        traj.metadata["usage"] = total_usage
        traj.metadata["finish_reason"] = completion.finish_reason
        # Verify first so that reward functions can use traj.success.
        if self.verify_fn:
            traj.success = self.verify_fn(traj)
        if self.reward_fn:
            traj.reward = self.reward_fn(traj)
        return traj

    # -- batch -------------------------------------------------------------
    def run_many(self, tasks: List[str]) -> List[Trajectory]:
        return [self.run(t) for t in tasks]


__all__ = ["AgentRunner", "RunConfig"]
