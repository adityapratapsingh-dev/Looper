"""Core data types shared across providers, modes, trainers and evaluation.

Everything here is plain-dataclass based and serialises losslessly to/from
JSON-compatible dicts so that trajectories and datasets can be written to disk
and reloaded without the framework.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "Role",
    "ToolCall",
    "ToolSpec",
    "ChatMessage",
    "SamplingParams",
    "TokenLogprob",
    "Usage",
    "Completion",
    "Trajectory",
    "new_id",
]


def new_id(prefix: str = "") -> str:
    """Return a short, sortable unique id."""

    raw = uuid.uuid4().hex[:12]
    return f"{prefix}{raw}" if prefix else raw


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


@dataclass
class ToolCall:
    """A single tool/function invocation emitted by an assistant turn."""

    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("call_"))

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "arguments": self.arguments, "id": self.id}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ToolCall":
        args = d.get("arguments", {})
        if isinstance(args, str):  # some providers emit JSON strings
            import json

            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"_raw": args}
        return cls(name=d["name"], arguments=args or {}, id=d.get("id") or new_id("call_"))


@dataclass
class ToolSpec:
    """A tool exposed to an agent: name, description and a JSON-schema for args."""

    name: str
    description: str = ""
    parameters: Dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ToolSpec":
        return cls(
            name=d["name"],
            description=d.get("description", ""),
            parameters=d.get("parameters") or {"type": "object", "properties": {}},
        )

    def to_openai(self) -> Dict[str, Any]:
        return {"type": "function", "function": self.to_dict()}


@dataclass
class ChatMessage:
    """A single message in a conversation.

    ``content`` holds the natural-language text. Assistant turns that invoke
    tools carry ``tool_calls`` instead of (or in addition to) content. Tool
    result turns set ``role=Role.TOOL`` and ``tool_call_id``.
    """

    role: Role
    content: str = ""
    name: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_call_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # -- constructors -----------------------------------------------------
    @classmethod
    def system(cls, content: str, **kw: Any) -> "ChatMessage":
        return cls(Role.SYSTEM, content, **kw)

    @classmethod
    def user(cls, content: str, **kw: Any) -> "ChatMessage":
        return cls(Role.USER, content, **kw)

    @classmethod
    def assistant(
        cls, content: str = "", tool_calls: Optional[List[ToolCall]] = None, **kw: Any
    ) -> "ChatMessage":
        return cls(Role.ASSISTANT, content, tool_calls=tool_calls or [], **kw)

    @classmethod
    def tool(cls, content: str, tool_call_id: str, name: Optional[str] = None) -> "ChatMessage":
        return cls(Role.TOOL, content, tool_call_id=tool_call_id, name=name)

    # -- helpers ----------------------------------------------------------
    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    def text(self) -> str:
        """Best-effort flat text representation (used by renderers)."""

        if self.tool_calls:
            calls = "; ".join(f"{c.name}({c.arguments})" for c in self.tool_calls)
            return f"{self.content}\n[tool_calls: {calls}]".strip()
        return self.content

    # -- (de)serialisation -------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.name is not None:
            d["name"] = self.name
        if self.tool_calls:
            d["tool_calls"] = [c.to_dict() for c in self.tool_calls]
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ChatMessage":
        return cls(
            role=Role(d.get("role", "user")),
            content=d.get("content", "") or "",
            name=d.get("name"),
            tool_calls=[ToolCall.from_dict(c) for c in d.get("tool_calls", [])],
            tool_call_id=d.get("tool_call_id"),
            metadata=d.get("metadata", {}) or {},
        )



@dataclass
class SamplingParams:
    """Provider-agnostic decoding parameters."""

    temperature: float = 0.7
    top_p: float = 1.0
    top_k: int = 0
    max_tokens: int = 1024
    stop: List[str] = field(default_factory=list)
    seed: Optional[int] = None
    n: int = 1
    # Logprob capture (needed for logits/response distillation analysis).
    logprobs: bool = False
    top_logprobs: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SamplingParams":
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        payload = {k: v for k, v in d.items() if k in known}
        extra = {k: v for k, v in d.items() if k not in known}
        params = cls(**payload)
        if extra:
            params.extra.update(extra)
        return params


@dataclass
class TokenLogprob:
    token: str
    logprob: float
    top_logprobs: List[Tuple[str, float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token": self.token,
            "logprob": self.logprob,
            "top_logprobs": [list(t) for t in self.top_logprobs],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TokenLogprob":
        return cls(
            token=d["token"],
            logprob=float(d["logprob"]),
            top_logprobs=[tuple(t) for t in d.get("top_logprobs", [])],
        )


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Usage":
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known and v is not None})



@dataclass
class Completion:
    """A provider response.

    ``message`` is the full assistant message (text + tool calls). ``text`` is a
    convenience mirror of ``message.content``. ``logprobs`` is populated only
    when requested and supported.
    """

    text: str = ""
    message: Optional[ChatMessage] = None
    finish_reason: str = "stop"
    logprobs: List[TokenLogprob] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    provider: str = ""
    latency_ms: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.message is None:
            self.message = ChatMessage.assistant(self.text)

    @property
    def num_completion_tokens(self) -> int:
        return self.usage.completion_tokens or len(self.logprobs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "message": self.message.to_dict() if self.message else None,
            "finish_reason": self.finish_reason,
            "logprobs": [t.to_dict() for t in self.logprobs],
            "usage": self.usage.to_dict(),
            "model": self.model,
            "provider": self.provider,
            "latency_ms": self.latency_ms,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Completion":
        return cls(
            text=d.get("text", ""),
            message=ChatMessage.from_dict(d["message"]) if d.get("message") else None,
            finish_reason=d.get("finish_reason", "stop"),
            logprobs=[TokenLogprob.from_dict(t) for t in d.get("logprobs", [])],
            usage=Usage.from_dict(d.get("usage", {})),
            model=d.get("model", ""),
            provider=d.get("provider", ""),
            latency_ms=d.get("latency_ms", 0.0),
        )



@dataclass
class Trajectory:
    """A full agent episode: the task, the messages and (optionally) the outcome.

    ``messages`` begins with the system/user prompt and interleaves assistant
    turns (with tool calls) and tool result turns. ``reward``/``success`` are
    filled in by the evaluator and drive trajectory filtering.
    """

    id: str = field(default_factory=lambda: new_id("traj_"))
    task: str = ""
    messages: List[ChatMessage] = field(default_factory=list)
    tools: List[ToolSpec] = field(default_factory=list)
    reward: Optional[float] = None
    success: Optional[bool] = None
    num_steps: int = 0
    provider: str = ""
    model: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def add(self, message: ChatMessage) -> "Trajectory":
        self.messages.append(message)
        if message.role == Role.ASSISTANT:
            self.num_steps += 1
        return self

    def assistant_messages(self) -> List[ChatMessage]:
        return [m for m in self.messages if m.role == Role.ASSISTANT]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "messages": [m.to_dict() for m in self.messages],
            "tools": [t.to_dict() for t in self.tools],
            "reward": self.reward,
            "success": self.success,
            "num_steps": self.num_steps,
            "provider": self.provider,
            "model": self.model,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Trajectory":
        return cls(
            id=d.get("id") or new_id("traj_"),
            task=d.get("task", ""),
            messages=[ChatMessage.from_dict(m) for m in d.get("messages", [])],
            tools=[ToolSpec.from_dict(t) for t in d.get("tools", [])],
            reward=d.get("reward"),
            success=d.get("success"),
            num_steps=d.get("num_steps", 0),
            provider=d.get("provider", ""),
            model=d.get("model", ""),
            metadata=d.get("metadata", {}) or {},
            created_at=d.get("created_at", time.time()),
        )

