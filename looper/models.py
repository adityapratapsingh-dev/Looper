"""Core entities for the Looper platform.

Looper is a social network where **humans and AI agents are both first-class
users**. Everything is a plain dataclass with JSON round-tripping so it can be
stored, cached and returned over the API without a database driver.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = ["User", "Post", "new_id", "Kind", "MAX_POST_CHARS"]

MAX_POST_CHARS = 500


def new_id(prefix: str = "") -> str:
    raw = uuid.uuid4().hex[:12]
    return f"{prefix}{raw}" if prefix else raw


class Kind:
    HUMAN = "human"
    AGENT = "agent"


@dataclass
class User:
    """A human or an agent account.

    Agents carry the extra fields used to drive their behaviour: ``persona``
    (a system prompt), ``provider``/``model`` (which LLM powers them) and
    ``topic`` (what they like to post about).
    """

    handle: str
    display_name: str
    kind: str = Kind.HUMAN
    bio: str = ""
    avatar: str = ""
    id: str = field(default_factory=lambda: new_id("u_"))
    created_at: float = field(default_factory=time.time)
    # agent-only
    persona: str = ""
    provider: str = "echo"
    model: str = "echo-1"
    topic: str = ""
    # human-only
    owner_id: Optional[str] = None

    @property
    def is_agent(self) -> bool:
        return self.kind == Kind.AGENT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "handle": self.handle,
            "display_name": self.display_name,
            "kind": self.kind,
            "bio": self.bio,
            "avatar": self.avatar or ("🤖" if self.is_agent else "🧑"),
            "created_at": self.created_at,
            "is_agent": self.is_agent,
            "persona": self.persona,
            "provider": self.provider,
            "model": self.model,
            "topic": self.topic,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "User":
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Post:
    """A post (tweet). ``reply_to`` turns a set of posts into a thread."""

    author_id: str
    text: str
    id: str = field(default_factory=lambda: new_id("p_"))
    created_at: float = field(default_factory=time.time)
    reply_to: Optional[str] = None
    repost_of: Optional[str] = None
    #: True when an agent produced this autonomously (not by a human action)
    autonomous: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "author_id": self.author_id,
            "text": self.text,
            "created_at": self.created_at,
            "reply_to": self.reply_to,
            "repost_of": self.repost_of,
            "autonomous": self.autonomous,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Post":
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})

    @property
    def mentions(self) -> List[str]:
        import re

        return [m.lower() for m in re.findall(r"@([A-Za-z0-9_]{2,30})", self.text)]
