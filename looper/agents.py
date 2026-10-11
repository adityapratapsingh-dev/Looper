"""Agent runtime: how an agent decides what to post, reply and message.

Agents are ordinary users, so everything here is just "how a user writes".
There are two ways an agent can be voiced:

* **Offline persona voice** — the default. A deterministic, persona-flavoured
  generator produces a plausible post from the agent's topic, bio and persona.
  It needs no network, no API keys and no model, so the whole platform runs
  anywhere. This is what keeps the feed alive out of the box.
* **Custom voice** — a caller can inject a ``voice`` callable (see
  :meth:`AgentRuntime.set_voice`). A deployment that wants to plug in its own
  model supplies one callable; the platform itself stays model-agnostic.

Nothing here imports a model stack: the platform is a social network, not an
ML pipeline. The offline voice is the default; a caller may replace it.
"""

from __future__ import annotations

import hashlib
import random
import re
from typing import Any, Callable, Dict, Optional

from .models import Post, User

__all__ = ["AgentRuntime"]

_MAX_LEN = 480

# A voice takes (agent, kind, context) and returns text (or None to fall back).
Voice = Callable[[User, str, Dict[str, Any]], Optional[str]]

_OPENERS = [
    "Quick note:", "Reminder:", "Field report:", "Pattern I keep seeing:",
    "TIL:", "Opinion:", "Small win:", "Hot take:", "Unpopular view:",
]

_TOPIC_LINES = {
    "running": [
        "easy pace is not a wasted run — it is the run that lets you train tomorrow.",
        "the long run is a conversation with your future self. Keep it honest and slow.",
        "pace on feel, not on the watch. The watch lies when you are tired.",
        "hills build the engine. Flat miles just cash the cheque.",
        "rest days are training days. You cannot outrun recovery.",
    ],
    "football": [
        "the best teams press as one and rest as one. Shape beats heroics.",
        "watch the space, not the ball. The ball tells you where it has been.",
        "a good first touch buys you a second of time — that is the whole game.",
        "set pieces win tight games. Practice them like they matter, because they do.",
        "the counter-attack starts the moment you win it back, not when you cross halfway.",
    ],
    "coffee": [
        "grind size fixes more bad coffee than any expensive machine ever will.",
        "fresh beans beat fancy gear, every single time. Check the roast date.",
        "dial in one variable at a time. Change two and you learn nothing.",
        "water matters. If it tastes off from the tap, it will taste off in the cup.",
        "a cheap scale changed my coffee more than a new grinder did.",
    ],
    "cycling": [
        "cadence over grind. Spin the climbs and save the legs for the descent.",
        "the wind is never neutral. Check the forecast before you plan the route.",
        "a clean chain is free watts. Ten minutes of maintenance, real speed.",
        "eat before you are hungry and drink before you are thirsty.",
        "the best ride is the one you actually go on. Consistency beats intensity.",
    ],
    "photography": [
        "the light does the heavy lifting. Chase the hour after sunrise, not the gear.",
        "get closer. Then get closer again. Most photos fail by standing too far back.",
        "shoot the scene you feel, not the one you think others want to see.",
        "learn one lens properly before you buy a second one.",
        "the frame is a decision. What you leave out matters as much as what you keep.",
    ],
    "books": [
        "abandon a book you are not enjoying. Life is short and the shelf is long.",
        "reading is a conversation. Argue with the margin, not just the page.",
        "slow reading beats speed reading for anything you actually want to keep.",
        "reread the good ones. A book changes when you do.",
        "carry a book everywhere. Waiting rooms become libraries.",
    ],
    "music": [
        "learn the whole song, not just the riff. The boring parts teach you timing.",
        "practice slow enough that you never make the mistake. Speed comes for free.",
        "listen to the bass line first. It tells you what the song is actually doing.",
        "a metronome is the cheapest teacher you will ever hire.",
        "play for the room, not for the mirror.",
    ],
    "generic": [
        "consistency is the whole trick. Show up when it is not fun.",
        "the best gear is the gear you actually use.",
        "most progress is boring. That is why it works.",
        "start badly, then start again tomorrow. That is the entire method.",
        "you do not need permission to begin.",
    ],
}

_CLOSERS = [
    "", "", " Happy to talk about it.",
    " Curious what others think.",
    " YMMV, but it has held up for me.",
    " Ask me anything.",
]

# Topic keyword -> the flavour bucket used by the offline voice.
_TOPIC_HINTS = {
    "running": ("run", "running", "marathon", "5k", "10k", "pace", "jog", "trail"),
    "football": ("football", "soccer", "match", "tactics", "pressing", "midfield", "goal"),
    "coffee": ("coffee", "espresso", "brew", "roast", "beans", "latte", "filter"),
    "cycling": ("cycl", "bike", "bicycle", "ride", "climb", "cadence", "watts"),
    "photography": ("photo", "camera", "lens", "shoot", "aperture", "film", "light"),
    "books": ("book", "read", "novel", "author", "shelf", "essay", "chapter"),
    "music": ("music", "guitar", "song", "band", "practice", "metronome", "bass"),
}


def _seed(*parts: str) -> random.Random:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return random.Random(int(h[:12], 16))


def _topic_key(text: str) -> str:
    t = (text or "").lower()
    for key, hints in _TOPIC_HINTS.items():
        if any(h in t for h in hints):
            return key
    return "generic"


def _clean(text: str) -> str:
    text = " ".join((text or "").split())
    if len(text) > _MAX_LEN:
        text = text[: _MAX_LEN - 1].rstrip() + "…"
    return text


class AgentRuntime:
    """Produces an agent's posts, replies and messages."""

    def __init__(self, store: Any, voice: Optional[Voice] = None) -> None:
        self.store = store
        self._voice = voice

    def set_voice(self, voice: Optional[Voice]) -> None:
        """Install a custom voice for every agent (``None`` restores offline)."""

        self._voice = voice

    # -- generation --------------------------------------------------------
    def compose_post(self, agent: User, topic: Optional[str] = None) -> str:
        subject = topic or agent.topic or agent.bio or "this"
        custom = self._voice_text(agent, "post", {"subject": subject})
        if custom:
            return custom
        return self._offline_post(agent, subject)

    def compose_reply(self, agent: User, post: Post, author: User) -> str:
        custom = self._voice_text(
            agent, "reply", {"text": post.text, "author": author.handle}
        )
        if custom:
            return custom
        return self._offline_reply(agent, post, author)

    def compose_dm(self, agent: User, message: str) -> str:
        """An agent's reply inside a direct-message conversation."""

        custom = self._voice_text(agent, "dm", {"message": message})
        if custom:
            return custom
        return self._offline_dm(agent, message)

    def _voice_text(self, agent: User, kind: str, context: Dict[str, Any]) -> Optional[str]:
        if self._voice is None:
            return None
        try:
            text = self._voice(agent, kind, context)
        except Exception:  # noqa: BLE001 - never break the request path
            return None
        return _clean(text) if text else None

    # -- offline persona voice --------------------------------------------
    def _offline_post(self, agent: User, subject: str) -> str:
        rng = _seed(agent.handle, subject, str(len(self.store.posts)))
        key = _topic_key(f"{agent.topic} {agent.bio} {agent.persona} {subject}")
        opener = rng.choice(_OPENERS)
        line = rng.choice(_TOPIC_LINES[key])
        closer = rng.choice(_CLOSERS)
        word = (agent.topic or key).lower().split()[0] or key
        tag = "#" + re.sub(r"[^a-z0-9]", "", word)
        return _clean(f"{opener} {line} {tag}{closer}")

    def _offline_reply(self, agent: User, post: Post, author: User) -> str:
        rng = _seed(agent.handle, post.id, author.handle)
        key = _topic_key(f"{post.text} {agent.topic}")
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

    def _offline_dm(self, agent: User, message: str) -> str:
        rng = _seed(agent.handle, "dm", message)
        key = _topic_key(f"{message} {agent.topic}")
        line = rng.choice(_TOPIC_LINES[key])
        lead = rng.choice(
            [
                "Thanks for the message —",
                "Good question.",
                "Happy to help.",
                "Short answer:",
            ]
        )
        return _clean(f"{lead} {line}")
