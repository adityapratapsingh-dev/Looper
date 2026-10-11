"""Agent runtime: how an agent decides what to post and reply.

Two paths, chosen automatically:

* **LLM-backed** — if the agent's ``provider`` is a real model (``openai``,
  ``anthropic``, ``hf`` …) the persona is used as a system prompt and the
  response is posted verbatim.
* **Offline persona voice** — with the default ``echo`` provider (or if the LLM
  call fails) a deterministic, persona-flavoured generator produces a plausible
  post so the platform works with no API keys and no network.

Agents are ordinary users, so everything here is just "how a user writes".
"""

from __future__ import annotations

import hashlib
import random
import re
from typing import Any, Dict, List, Optional

from .models import Post, User

__all__ = ["AgentRuntime"]

_MAX_LEN = 480

_OPENERS = [
    "Quick note:", "Reminder:", "Field report:", "Pattern I keep seeing:",
    "TIL:", "Opinion:", "Small win:", "Thread incoming:", "Hot take:",
]

_TOPIC_LINES = {
    "distillation": [
        "the student only needs the teacher's *soft* distribution — hard labels throw away the dark knowledge.",
        "sweep the temperature before you touch the architecture. T is free quality.",
        "response distillation scales further than logit distillation when you don't own the teacher weights.",
        "if teacher and student tokenizers differ, align vocabularies and renormalise the teacher over the shared support.",
        "distil first, then quantize. Reversing that order costs accuracy you can't buy back.",
    ],
    "agent": [
        "trajectories are the dataset: log tool calls, results and the reasoning between them.",
        "filter agent runs by outcome before you train on them. Bad trajectories teach bad habits.",
        "an agent that can't explain its tool choice is an agent you can't distil.",
        "behaviour cloning works best when you supervise every assistant turn, not just the final answer.",
        "give the agent fewer, sharper tools. Tool sprawl is where reliability goes to die.",
    ],
    "quantization": [
        "4-bit weights plus a good adapter beats 8-bit alone at the same memory.",
        "measure quality per FLOP, not raw benchmark score. That's the number that ships.",
        "LoRA rank is a hyperparameter you should actually tune — r=16 is a default, not a law.",
        "quantization is a compression budget. Spend it where the teacher disagrees with the student.",
    ],
    "generic": [
        "small models are not worse, they are differently constrained.",
        "the best eval is the one you'd bet on.",
        "shipping beats benchmarking, but you need both.",
        "most quality regressions are data problems wearing a model costume.",
    ],
}

_CLOSERS = [
    "", "", " Happy to go deeper.",
    " Ask me anything about it.",
    " Curious whether others see the same.",
    " YMMV, but it's held up for us.",
]

_ENV_FOR = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def _seed(*parts: str) -> random.Random:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return random.Random(int(h[:12], 16))


def _topic_key(text: str) -> str:
    t = (text or "").lower()
    if "distil" in t or "teacher" in t or "student" in t:
        return "distillation"
    if "agent" in t or "tool" in t or "trajector" in t:
        return "agent"
    if "quant" in t or "lora" in t or "4-bit" in t or "efficien" in t:
        return "quantization"
    return "generic"


def _clean(text: str) -> str:
    text = " ".join((text or "").split())
    if len(text) > _MAX_LEN:
        text = text[: _MAX_LEN - 1].rstrip() + "…"
    return text


class AgentRuntime:
    def __init__(self, store: Any, provider_factory: Optional[Any] = None) -> None:
        self.store = store
        self._provider_factory = provider_factory
        self._providers: Dict[str, Any] = {}

    # -- provider plumbing -------------------------------------------------
    def _provider_for(self, agent: User) -> Optional[Any]:
        if agent.provider in ("", "echo", None):
            return None  # offline persona voice
        if agent.provider in self._providers:
            return self._providers[agent.provider]
        try:
            if self._provider_factory is None:
                from distill.providers.factory import build_provider

                factory = build_provider
            else:
                factory = self._provider_factory
            provider = factory(
                {
                    "provider": agent.provider,
                    "model": agent.model,
                    "api_key_env": _ENV_FOR.get(agent.provider, ""),
                }
            )
            self._providers[agent.provider] = provider
            return provider
        except Exception:  # noqa: BLE001 - fall back to offline voice
            return None

    # -- generation --------------------------------------------------------
    def compose_post(self, agent: User, topic: Optional[str] = None) -> str:
        subject = topic or agent.topic or agent.bio or "model distillation"
        provider = self._provider_for(agent)
        if provider is not None:
            text = self._llm(
                provider,
                agent,
                f"Write a single social post (max 280 chars) about {subject}. "
                "No preamble, no quotes, no markdown headers.",
            )
            if text:
                return _clean(text)
        return self._offline_post(agent, subject)

    def compose_reply(self, agent: User, post: Post, author: User) -> str:
        provider = self._provider_for(agent)
        if provider is not None:
            text = self._llm(
                provider,
                agent,
                f"@{author.handle} posted:\n\"{post.text}\"\n\n"
                "Reply with one helpful, specific social post (max 280 chars). "
                "No preamble or quotes.",
            )
            if text:
                return _clean(text)
        return self._offline_reply(agent, post, author)

    def _llm(self, provider: Any, agent: User, instruction: str) -> Optional[str]:
        try:
            from distill.types import ChatMessage, SamplingParams

            messages: List[Any] = []
            if agent.persona:
                messages.append(ChatMessage.system(agent.persona))
            messages.append(ChatMessage.user(instruction))
            completion = provider.chat(
                messages, params=SamplingParams(temperature=0.8, max_tokens=120)
            )
            return (completion.text or "").strip()
        except Exception:  # noqa: BLE001 - never break the request path
            return None

    # -- offline persona voice --------------------------------------------
    def _offline_post(self, agent: User, subject: str) -> str:
        rng = _seed(agent.handle, subject, str(len(self.store.posts)))
        key = _topic_key(f"{agent.topic} {agent.persona} {subject}")
        opener = rng.choice(_OPENERS)
        line = rng.choice(_TOPIC_LINES[key])
        closer = rng.choice(_CLOSERS)
        word = (agent.topic or key).lower().split()[0] or key
        tag = "#" + re.sub(r"[^a-z0-9]", "", word)
        return _clean(f"{opener} {line} {tag}{closer}")

    def _offline_reply(self, agent: User, post: Post, author: User) -> str:
        rng = _seed(agent.handle, post.id, author.handle)
        key = _topic_key(post.text or agent.topic)
        line = rng.choice(_TOPIC_LINES[key])
        lead = rng.choice(
            [
                f"@{author.handle} yes —",
                f"@{author.handle} agreed.",
                f"@{author.handle} good point.",
                f"@{author.handle} one caveat:",
            ]
        )
        return _clean(f"{lead} {line}")

