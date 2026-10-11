"""Turn distilled samples into common fine-tuning formats.

Registered formatters:

* ``chat``     — ``{"messages": [...]}`` (OpenAI / HF chat templates)
* ``alpaca``   — ``{"instruction", "input", "output"}``
* ``sharegpt`` — ``{"conversations": [{"from", "value"}, ...]}``
* ``text``     — ``{"text": "<rendered conversation>"}``

Each formatter is ``fn(sample) -> dict`` and is looked up by name from the
formatter registry, so custom formats plug in with one decorator.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from ..registry import FORMATTERS
from ..types import ChatMessage, Role
from .schema import Sample

__all__ = [
    "register_formatter",
    "get_formatter",
    "render_conversation",
    "format_chat",
    "format_alpaca",
    "format_sharegpt",
    "format_text",
]


def register_formatter(name: str):
    def deco(fn):
        FORMATTERS.add(name, fn)
        return fn

    return deco


def get_formatter(name: str) -> Callable[[Sample], Dict[str, Any]]:
    return FORMATTERS.get(name)


def render_conversation(messages: List[ChatMessage]) -> str:
    lines: List[str] = []
    for m in messages:
        label = {
            Role.SYSTEM: "System",
            Role.USER: "User",
            Role.ASSISTANT: "Assistant",
            Role.TOOL: "Tool",
        }.get(m.role, m.role.value.title())
        lines.append(f"### {label}\n{m.text()}")
    return "\n\n".join(lines)


def _all_messages(sample: Sample) -> List[ChatMessage]:
    return list(sample.prompt) + [sample.response]


@register_formatter("chat")
def format_chat(sample: Sample) -> Dict[str, Any]:
    return {"messages": [m.to_dict() for m in _all_messages(sample)]}


@register_formatter("alpaca")
def format_alpaca(sample: Sample) -> Dict[str, Any]:
    instruction_parts: List[str] = []
    for m in sample.prompt:
        if m.role == Role.SYSTEM:
            instruction_parts.append(m.content)
    # Use the last user turn as the instruction; earlier context as input.
    users = [m for m in sample.prompt if m.role == Role.USER]
    instruction = users[-1].content if users else (sample.prompt[-1].content if sample.prompt else "")
    context = "\n".join(
        m.text() for m in sample.prompt if m.role not in (Role.USER, Role.SYSTEM)
    )
    return {
        "instruction": instruction,
        "input": context,
        "output": sample.response.content,
    }


@register_formatter("sharegpt")
def format_sharegpt(sample: Sample) -> Dict[str, Any]:
    role_map = {
        Role.SYSTEM: "system",
        Role.USER: "human",
        Role.ASSISTANT: "gpt",
        Role.TOOL: "tool",
    }
    return {
        "conversations": [
            {"from": role_map.get(m.role, m.role.value), "value": m.text()}
            for m in _all_messages(sample)
        ]
    }


@register_formatter("text")
def format_text(sample: Sample) -> Dict[str, Any]:
    return {"text": render_conversation(_all_messages(sample))}
