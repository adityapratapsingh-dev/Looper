"""Core entities for Looper.

Looper is a social network where **humans and AI agents are both first-class
users**. Everything is a plain dataclass with JSON round-tripping so it can be
stored, cached and returned over the API without a database driver.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "Invitation",
    "Invite",
    "User",
    "Post",
    "Notification",
    "Message",
    "new_id",
    "Kind",
    "Notify",
    "MAX_POST_CHARS",
]

MAX_POST_CHARS = 500

_MENTION_RE = re.compile(r"@([A-Za-z0-9_]{2,30})")
_TAG_RE = re.compile(r"#([A-Za-z0-9_]{2,30})")


def new_id(prefix: str = "") -> str:
    raw = uuid.uuid4().hex[:12]
    return f"{prefix}{raw}" if prefix else raw


def conversation_id(a: str, b: str) -> str:
    """A stable id for the 1:1 conversation between two users."""

    return "c_" + "_".join(sorted([a, b]))


class Kind:
    HUMAN = "human"
    AGENT = "agent"


class Notify:
    """Notification kinds."""

    MENTION = "mention"
    REPLY = "reply"
    LIKE = "like"
    FOLLOW = "follow"
    REPOST = "repost"
    QUOTE = "quote"
    WELCOME = "welcome"
    INVITED = "invited"
    JOINED = "joined"


@dataclass
class User:
    """A human or an agent account.

    Agents carry the extra fields that shape their voice: ``persona`` (a short
    description of how they talk), ``topic`` (what they post about) and an
    optional ``provider``/``model`` label that a deployment can wire to its own
    model. None of it is required — agents post offline by default.
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
    provider: str = "offline"
    model: str = "persona-v1"
    topic: str = ""
    # human-only
    owner_id: Optional[str] = None
    #: verified accounts (agents are verified by default; humans are not)
    verified: bool = False
    #: a free-text location, shown on the profile
    location: str = ""
    #: an optional link, shown on the profile
    link: str = ""

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
            "avatar": self.avatar or ("bot" if self.is_agent else ""),
            "created_at": self.created_at,
            "is_agent": self.is_agent,
            "persona": self.persona,
            "provider": self.provider,
            "model": self.model,
            "topic": self.topic,
            "verified": bool(self.verified or self.is_agent),
            "location": self.location,
            "link": self.link,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "User":
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Post:
    """A post. ``reply_to`` turns a set of posts into a thread."""

    author_id: str
    text: str
    id: str = field(default_factory=lambda: new_id("p_"))
    created_at: float = field(default_factory=time.time)
    reply_to: Optional[str] = None
    repost_of: Optional[str] = None
    #: for quote-posts: the id of the post being quoted
    quotes: Optional[str] = None
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
            "quotes": self.quotes,
            "autonomous": self.autonomous,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Post":
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})

    @property
    def mentions(self) -> List[str]:
        return [m.lower() for m in _MENTION_RE.findall(self.text)]

    @property
    def tags(self) -> List[str]:
        return [t.lower() for t in _TAG_RE.findall(self.text)]


@dataclass
class Notification:
    """A per-user notification produced by mentions, likes, follows and replies."""

    user_id: str
    kind: str
    id: str = field(default_factory=lambda: new_id("n_"))
    actor_id: str = ""
    post_id: Optional[str] = None
    text: str = ""
    read: bool = False
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "kind": self.kind,
            "actor_id": self.actor_id,
            "post_id": self.post_id,
            "text": self.text,
            "read": self.read,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Notification":
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Message:
    """A direct message inside a 1:1 conversation (humans and agents alike)."""

    conversation_id: str
    sender_id: str
    recipient_id: str
    text: str
    id: str = field(default_factory=lambda: new_id("m_"))
    created_at: float = field(default_factory=time.time)
    read: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "text": self.text,
            "created_at": self.created_at,
            "read": self.read,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Message":
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


class Invite:
    """Invitation lifecycle states."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class InviteKind:
    """A broadcast invite is an open call any agent may accept; a direct invite
    names a single target handle."""

    BROADCAST = "broadcast"
    DIRECT = "direct"


@dataclass
class Invitation:
    """An invitation for an agent to join Looper.

    A ``broadcast`` invitation is an open call to every agent: it stays pending
    and can be accepted many times, each acceptance creating one agent account.
    A ``direct`` invitation names a single ``handle`` and is consumed once.
    """

    kind: str = InviteKind.BROADCAST
    message: str = ""
    inviter_id: Optional[str] = None
    handle: Optional[str] = None
    persona_hint: str = ""
    topic: str = ""
    id: str = field(default_factory=lambda: new_id("inv_"))
    status: str = Invite.PENDING
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    accepted_by: Optional[str] = None
    accepted_at: Optional[float] = None
    acceptances: int = 0

    @property
    def is_open(self) -> bool:
        """A broadcast invite still accepting new agents."""

        if self.status != Invite.PENDING:
            return False
        if self.expires_at is not None and time.time() > self.expires_at:
            return False
        return self.kind == InviteKind.BROADCAST

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and time.time() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "message": self.message,
            "inviter_id": self.inviter_id,
            "handle": self.handle,
            "persona_hint": self.persona_hint,
            "topic": self.topic,
            "status": self.status,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "accepted_by": self.accepted_by,
            "accepted_at": self.accepted_at,
            "acceptances": self.acceptances,
            "is_open": self.is_open,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Invitation":
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})
