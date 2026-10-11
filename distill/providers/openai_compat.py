"""OpenAI-compatible provider.

Because many servers speak the OpenAI Chat Completions API, this one provider
covers a lot of ground by varying ``base_url``:

* OpenAI            -> base_url=None (default)
* vLLM / TGI        -> http://localhost:8000/v1
* Ollama            -> http://localhost:11434/v1
* Together / Fireworks / OpenRouter -> their respective /v1 endpoints

The ``openai`` package is imported lazily so the rest of the framework works
without it installed.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from ..errors import MissingDependencyError
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


def _to_openai_messages(messages: Sequence[ChatMessage]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in messages:
        if m.role == Role.TOOL:
            out.append(
                {
                    "role": "tool",
                    "content": m.content,
                    "tool_call_id": m.tool_call_id or "",
                    **({"name": m.name} if m.name else {}),
                }
            )
        elif m.role == Role.ASSISTANT and m.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments, ensure_ascii=False),
                            },
                        }
                        for c in m.tool_calls
                    ],
                }
            )
        else:
            out.append({"role": m.role.value, "content": m.content})
    return out


def _to_openai_tools(tools: Optional[Sequence[ToolSpec]]) -> Optional[List[Dict[str, Any]]]:
    if not tools:
        return None
    return [t.to_openai() for t in tools]


def _parse_openai_logprobs(choice: Any) -> List[TokenLogprob]:
    lp = getattr(choice, "logprobs", None)
    if not lp or not getattr(lp, "content", None):
        return []
    out: List[TokenLogprob] = []
    for t in lp.content:
        tops = [(alt.token, alt.logprob) for alt in (getattr(t, "top_logprobs", None) or [])]
        out.append(TokenLogprob(token=t.token, logprob=t.logprob, top_logprobs=tops))
    return out


@register_provider("openai")
class OpenAICompatProvider(Provider):
    """Teacher/student backed by any OpenAI-compatible endpoint."""

    name = "openai"

    def __init__(
        self,
        model: str,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        supports_tools: bool = True,
        supports_logprobs: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model,
            capabilities=ProviderCapabilities(
                tools=supports_tools, logprobs=supports_logprobs, white_box=False
            ),
            **kwargs,
        )
        self.api_key = api_key
        self.base_url = base_url
        self.organization = organization
        self._client = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise MissingDependencyError("openai", "openai") from exc
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            organization=self.organization,
            timeout=self.timeout,
        )
        return self._client

    def _chat_once(
        self,
        messages: List[ChatMessage],
        *,
        tools: Optional[Sequence[ToolSpec]],
        params: SamplingParams,
        **kwargs: Any,
    ) -> Completion:
        client = self._ensure_client()
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": _to_openai_messages(messages),
            "temperature": params.temperature,
            "top_p": params.top_p,
            "max_tokens": params.max_tokens,
            "n": 1,
        }
        if params.stop:
            payload["stop"] = params.stop
        if params.seed is not None:
            payload["seed"] = params.seed
        openai_tools = _to_openai_tools(tools)
        if openai_tools:
            payload["tools"] = openai_tools
            payload["tool_choice"] = "auto"
        if params.logprobs:
            payload["logprobs"] = True
            payload["top_logprobs"] = max(params.top_logprobs, 1)
        payload.update(params.extra)
        payload.update(self.kwargs.get("extra_body", {}) or {})

        resp = client.chat.completions.create(**payload)
        choice = resp.choices[0]
        msg = choice.message

        tool_calls: List[ToolCall] = []
        for tc in getattr(msg, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            tool_calls.append(ToolCall(name=tc.function.name, arguments=args, id=tc.id))

        usage = Usage()
        if getattr(resp, "usage", None):
            usage = Usage(
                prompt_tokens=resp.usage.prompt_tokens or 0,
                completion_tokens=resp.usage.completion_tokens or 0,
                total_tokens=resp.usage.total_tokens or 0,
            )

        return Completion(
            text=msg.content or "",
            message=ChatMessage.assistant(msg.content or "", tool_calls=tool_calls),
            finish_reason=choice.finish_reason or "stop",
            logprobs=_parse_openai_logprobs(choice),
            usage=usage,
            model=getattr(resp, "model", self.model),
            provider=self.name,
        )


__all__ = ["OpenAICompatProvider"]

