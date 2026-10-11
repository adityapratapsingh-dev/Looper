"""Anthropic Claude provider (Messages API).

Handles the small API differences from OpenAI: the system prompt is a top-level
parameter, tool schemas use ``input_schema`` (not ``function`` nesting), and the
assistant response is a list of content blocks (text + ``tool_use``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ..errors import MissingDependencyError
from ..types import ChatMessage, Completion, Role, SamplingParams, ToolCall, ToolSpec, Usage
from .base import Provider, ProviderCapabilities, register_provider


def _split_system(messages: Sequence[ChatMessage]) -> tuple[Optional[str], List[Dict[str, Any]]]:
    system_parts: List[str] = []
    convo: List[Dict[str, Any]] = []
    for m in messages:
        if m.role == Role.SYSTEM:
            system_parts.append(m.content)
            continue
        if m.role == Role.TOOL:
            convo.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.tool_call_id or "",
                            "content": m.content,
                        }
                    ],
                }
            )
        elif m.role == Role.ASSISTANT and m.tool_calls:
            blocks: List[Dict[str, Any]] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for c in m.tool_calls:
                blocks.append(
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                )
            convo.append({"role": "assistant", "content": blocks})
        else:
            convo.append({"role": m.role.value, "content": m.content})
    return ("\n\n".join(system_parts) or None), convo


@register_provider("anthropic")
class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(
        self,
        model: str,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        supports_tools: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model,
            capabilities=ProviderCapabilities(tools=supports_tools, logprobs=False),
            **kwargs,
        )
        self.api_key = api_key
        self.base_url = base_url
        self._client = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from anthropic import Anthropic  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise MissingDependencyError("anthropic", "anthropic") from exc
        kw: Dict[str, Any] = {"timeout": self.timeout}
        if self.api_key:
            kw["api_key"] = self.api_key
        if self.base_url:
            kw["base_url"] = self.base_url
        self._client = Anthropic(**kw)
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
        system, convo = _split_system(messages)
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": convo,
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
        }
        if system:
            payload["system"] = system
        if params.stop:
            payload["stop_sequences"] = params.stop
        if tools:
            payload["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ]
        payload.update(params.extra)

        resp = client.messages.create(**payload)
        text_parts: List[str] = []
        tool_calls: List[ToolCall] = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
            elif getattr(block, "type", None) == "tool_use":
                tool_calls.append(
                    ToolCall(name=block.name, arguments=dict(block.input or {}), id=block.id)
                )
        text = "".join(text_parts)
        usage = Usage(
            prompt_tokens=getattr(resp.usage, "input_tokens", 0) or 0,
            completion_tokens=getattr(resp.usage, "output_tokens", 0) or 0,
        )
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        return Completion(
            text=text,
            message=ChatMessage.assistant(text, tool_calls=tool_calls),
            finish_reason=getattr(resp, "stop_reason", "stop") or "stop",
            usage=usage,
            model=getattr(resp, "model", self.model),
            provider=self.name,
        )


__all__ = ["AnthropicProvider"]
