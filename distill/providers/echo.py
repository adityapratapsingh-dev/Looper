"""A dependency-free, deterministic provider for tests, offline demos and CI.

``EchoProvider`` needs no network and no API keys. It can:

* echo/transform the last user message,
* emit tool calls when tools are supplied and the prompt looks like it wants one,
* synthesise plausible top-k logprobs, and
* expose a fake next-token distribution (white-box) so logits-mode code paths
  are exercisable without a GPU.

It is intentionally simple but *deterministic given a seed*, which makes it a
good stand-in for assertions in the test-suite.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Dict, List, Optional, Sequence

from ..types import (
    ChatMessage,
    Completion,
    Role,
    SamplingParams,
    TokenLogprob,
    ToolCall,
    ToolSpec,
    Usage,
)
from .base import Provider, ProviderCapabilities, register_provider

_CANNED_VOCAB = [
    " the", " a", " answer", " result", " yes", " no", " because",
    " first", " then", " finally", " data", " model", " agent", " tool",
]

_TOOL_HINTS = ("call", "use tool", "invoke", "run ", "search", "calculate", "look up")


def _seed_from(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**31)


def _softmax(scores: Dict[str, float]) -> Dict[str, float]:
    if not scores:
        return {}
    m = max(scores.values())
    exps = {k: math.exp(v - m) for k, v in scores.items()}
    total = sum(exps.values()) or 1.0
    return {k: v / total for k, v in exps.items()}


@register_provider("echo")
class EchoProvider(Provider):
    """Deterministic offline provider."""

    name = "echo"

    def __init__(
        self,
        model: str = "echo-1",
        *,
        echo_prefix: str = "",
        prefer_tools: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model,
            capabilities=ProviderCapabilities(tools=True, logprobs=True, white_box=True),
            **kwargs,
        )
        self.echo_prefix = echo_prefix
        self.prefer_tools = prefer_tools

    def _chat_once(
        self,
        messages: List[ChatMessage],
        *,
        tools: Optional[Sequence[ToolSpec]],
        params: SamplingParams,
        **kwargs: Any,
    ) -> Completion:
        last_user = next((m for m in reversed(messages) if m.role == Role.USER), None)
        prompt = last_user.content if last_user else ""
        seed = _seed_from(f"{self.model}|{prompt}|{params.temperature}")

        tool_calls: List[ToolCall] = []
        if tools and self.prefer_tools and _looks_like_tool_request(prompt, messages):
            spec = list(tools)[seed % len(list(tools))]
            tool_calls.append(ToolCall(name=spec.name, arguments=_fake_arguments(prompt, spec)))

        if tool_calls:
            text = ""
        else:
            base = prompt.strip() or "hello"
            text = self.echo_prefix + _compose_answer(base, seed)

        logprobs = _fake_logprobs(text, params)
        usage = Usage(
            prompt_tokens=_count_prompt_tokens(messages),
            completion_tokens=max(len(logprobs), len(text.split())),
        )
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens

        return Completion(
            text=text,
            message=ChatMessage.assistant(text, tool_calls=tool_calls),
            finish_reason="tool_calls" if tool_calls else "stop",
            logprobs=logprobs,
            usage=usage,
            model=self.model,
            provider=self.name,
        )

    def next_token_distribution(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> Dict[str, float]:
        last = messages[-1].content if messages else ""
        seed = _seed_from(last)
        logits = {
            tok: math.sin(seed * 0.001 + i) + (len(_CANNED_VOCAB) - i) * 0.1
            for i, tok in enumerate(_CANNED_VOCAB)
        }
        return _softmax(logits)


# -- module-level helpers --------------------------------------------------
def _looks_like_tool_request(prompt: str, messages: List[ChatMessage]) -> bool:
    if messages and messages[-1].role == Role.TOOL:
        return False  # already have a tool result -> produce the final answer
    lowered = prompt.lower()
    return any(k in lowered for k in _TOOL_HINTS)


def _fake_arguments(prompt: str, spec: ToolSpec) -> Dict[str, Any]:
    props = (spec.parameters or {}).get("properties", {}) or {}
    args: Dict[str, Any] = {}
    for name, schema in props.items():
        typ = (schema or {}).get("type", "string")
        if typ == "integer":
            args[name] = _seed_from(prompt) % 100
        elif typ == "number":
            args[name] = round((_seed_from(prompt) % 100) / 10.0, 2)
        elif typ == "boolean":
            args[name] = _seed_from(prompt) % 2 == 0
        else:
            args[name] = prompt[:64] or "value"
    return args


def _compose_answer(prompt: str, seed: int) -> str:
    templates = [
        "Based on the input, the answer is: {p}",
        "Here is a concise response to '{p}'.",
        "Reasoning step 1: parse the question.\nReasoning step 2: answer: {p}",
    ]
    return templates[seed % len(templates)].format(p=prompt)


def _count_prompt_tokens(messages: List[ChatMessage]) -> int:
    return sum(max(1, len(m.content.split())) for m in messages)


def _fake_logprobs(text: str, params: SamplingParams) -> List[TokenLogprob]:
    """Deterministic pseudo-logprobs over whitespace tokens of ``text``."""

    if not (params.logprobs or params.top_logprobs) or not text:
        return []
    tokens = text.split() or [text]
    out: List[TokenLogprob] = []
    for i, tok in enumerate(tokens):
        seed = _seed_from(f"{tok}:{i}")
        # main token logprob in a plausible range
        lp = -abs(math.sin(seed * 0.01)) - 0.05
        tops = []
        if params.top_logprobs:
            for j in range(min(params.top_logprobs, len(_CANNED_VOCAB))):
                alt = _CANNED_VOCAB[(seed + j) % len(_CANNED_VOCAB)]
                tops.append((alt, lp - 0.1 * (j + 1)))
        out.append(TokenLogprob(token=tok, logprob=lp, top_logprobs=tops))
    return out


__all__ = ["EchoProvider"]

