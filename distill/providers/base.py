"""Provider base class, capabilities and registry helpers."""

from __future__ import annotations

import abc
import json
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..errors import ProviderError
from ..registry import PROVIDERS
from ..types import ChatMessage, Completion, SamplingParams, ToolSpec

__all__ = [
    "Provider",
    "ProviderCapabilities",
    "register_provider",
    "get_provider",
]


@dataclass
class ProviderCapabilities:
    """What a provider can do — used by modes to fail early with clear errors."""

    tools: bool = False
    logprobs: bool = False
    system_prompt: bool = True
    async_native: bool = False
    white_box: bool = False  # exposes full next-token distribution over the vocab


class Provider(abc.ABC):
    """Abstract teacher/student model endpoint.

    Concrete providers implement :meth:`_chat_once`. Retries, timing and usage
    bookkeeping are handled here so implementations stay thin.
    """

    #: registry name, e.g. "openai"
    name: str = "provider"

    def __init__(
        self,
        model: str,
        *,
        capabilities: Optional[ProviderCapabilities] = None,
        max_retries: int = 3,
        retry_backoff: float = 1.5,
        timeout: float = 120.0,
        **kwargs: Any,
    ) -> None:
        self.model = model
        self.capabilities = capabilities or ProviderCapabilities()
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.timeout = timeout
        self.kwargs = kwargs

    # -- public API --------------------------------------------------------
    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Optional[Sequence[ToolSpec]] = None,
        params: Optional[SamplingParams] = None,
        **kwargs: Any,
    ) -> Completion:
        """Generate one assistant turn with retries and timing."""

        params = params or SamplingParams()
        messages = list(messages)
        if tools and not self.capabilities.tools:
            raise ProviderError(
                f"Provider '{self.name}' does not support tools; got {len(list(tools))}."
            )
        if (params.logprobs or params.top_logprobs) and not self.capabilities.logprobs:
            # Not fatal — we simply cannot return logprobs. Warn through metadata.
            pass

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            start = time.perf_counter()
            try:
                completion = self._chat_once(messages, tools=tools, params=params, **kwargs)
                completion.provider = self.name
                completion.model = completion.model or self.model
                completion.latency_ms = (time.perf_counter() - start) * 1000.0
                return completion
            except Exception as exc:  # noqa: BLE001 - retried below
                last_err = exc
                if attempt >= self.max_retries:
                    break
                sleep = self.retry_backoff * (2**attempt) + random.random() * 0.1
                time.sleep(sleep)
        raise ProviderError(
            f"Provider '{self.name}' failed after {self.max_retries + 1} attempts: {last_err}"
        )

    def complete(
        self, prompt: str, *, params: Optional[SamplingParams] = None, **kwargs: Any
    ) -> Completion:
        """Single-turn convenience wrapper."""

        return self.chat([ChatMessage.user(prompt)], params=params, **kwargs)

    # -- white-box hook ----------------------------------------------------
    def next_token_distribution(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> Dict[str, float]:
        """Return the full (softmax) next-token distribution. White-box only.

        Providers without local weights raise :class:`ProviderError`; the logits
        mode uses :meth:`chat` with ``logprobs`` instead when this is unavailable.
        """

        raise ProviderError(
            f"Provider '{self.name}' does not expose the full next-token distribution. "
            "Use a local (white-box) provider for loss-level distillation."
        )

    # -- contract ----------------------------------------------------------
    @abc.abstractmethod
    def _chat_once(
        self,
        messages: List[ChatMessage],
        *,
        tools: Optional[Sequence[ToolSpec]],
        params: SamplingParams,
        **kwargs: Any,
    ) -> Completion:
        """Perform a single network/local generation. Implemented by subclasses."""

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<{type(self).__name__} name={self.name!r} model={self.model!r}>"


# -- registry helpers ------------------------------------------------------
def register_provider(name: str):
    """Decorator: register a provider class under ``name``."""

    return PROVIDERS.register(name)


def get_provider(name: str, *args: Any, **kwargs: Any) -> Provider:
    """Instantiate a provider by registry name."""

    return PROVIDERS.create(name, *args, **kwargs)


def summarize_messages(messages: Sequence[ChatMessage], limit: int = 400) -> str:
    """Compact JSON-ish summary of a transcript, useful for logs."""

    try:
        blob = json.dumps([m.to_dict() for m in messages], ensure_ascii=False)
    except Exception:  # noqa: BLE001
        blob = str([m.text() for m in messages])
    return blob if len(blob) <= limit else blob[: limit - 3] + "..."
