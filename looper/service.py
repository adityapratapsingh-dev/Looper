"""Service layer: the platform's operations, independent of HTTP.

Every method returns plain JSON-ready dicts, so the same code backs the
serverless API, the tests and any future CLI.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .agents import AgentRuntime
from .models import MAX_POST_CHARS, Kind, Post, User
from .store import Store

__all__ = ["Service", "serialize_post", "serialize_user"]


def serialize_user(store: Store, user: User, viewer: Optional[User] = None) -> Dict[str, Any]:
    d = user.to_dict()
    d.update(
        {
            "followers": len(store.followers(user.id)),
            "following": len(store.following(user.id)),
            "posts": len(store.user_posts(user.id)),
            "is_me": bool(viewer and viewer.id == user.id),
            "is_mine": bool(viewer and user.owner_id == viewer.id),
            "is_following": bool(viewer and store.is_following(viewer.id, user.id)),
        }
    )
    return d


def serialize_post(
    store: Store,
    post: Post,
    viewer: Optional[User] = None,
    *,
    include_replies: bool = False,
    limit_replies: int = 3,
) -> Dict[str, Any]:
    author = store.get_user(post.author_id)
    d = post.to_dict()
    replies = store.replies_to(post.id)
    likers = store.likers(post.id)
    d.update(
        {
            "author": serialize_user(store, author, viewer) if author else None,
            "likes": len(likers),
            "replies": len(replies),
            "liked": bool(viewer and viewer.id in likers),
            "mentions": post.mentions,
            "reply_to_author": None,
        }
    )
    if post.reply_to:
        parent = store.get_post(post.reply_to)
        parent_author = store.get_user(parent.author_id) if parent else None
        d["reply_to_author"] = parent_author.handle if parent_author else None
    if include_replies:
        d["reply_preview"] = [
            serialize_post(store, r, viewer) for r in replies[:limit_replies]
        ]
    return d


class Service:
    def __init__(self, store: Optional[Store] = None, runtime: Optional[AgentRuntime] = None) -> None:
        self.store = store or Store()
        self.runtime = runtime or AgentRuntime(self.store)

    # -- helpers -----------------------------------------------------------
    def _viewer(self, handle: Optional[str]) -> Optional[User]:
        """Resolve the acting user. There is no implicit default: an empty
        network means no viewer, and the client must onboard first."""

        return self.store.get_user(handle) if handle else None

    # -- reads -------------------------------------------------------------
    def bootstrap(self, handle: Optional[str] = None) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        return {
            "viewer": serialize_user(self.store, viewer, viewer) if viewer else None,
            "needs_onboarding": viewer is None,
            "stats": self.store.stats(),
            "trending": self.store.trending(),
            "suggested": [
                serialize_user(self.store, u, viewer)
                for u in self.store.list_users(Kind.AGENT)[:4]
            ],
        }

    def feed(self, mode: str = "for_you", handle: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        posts = self.store.feed(viewer.id if viewer else None, mode=mode, limit=limit)
        return {
            "mode": mode,
            "posts": [serialize_post(self.store, p, viewer) for p in posts],
        }

    def post_detail(self, post_id: str, handle: Optional[str] = None) -> Optional[Dict[str, Any]]:
        viewer = self._viewer(handle)
        post = self.store.get_post(post_id)
        if post is None:
            return None
        chain = self.store.thread(post_id)
        return {
            "thread": [serialize_post(self.store, p, viewer) for p in chain],
            "post": serialize_post(self.store, post, viewer),
            "replies": [
                serialize_post(self.store, r, viewer, include_replies=True)
                for r in self.store.replies_to(post_id)
            ],
        }

    def profile(self, handle: str, viewer_handle: Optional[str] = None, tab: str = "posts") -> Optional[Dict[str, Any]]:
        viewer = self._viewer(viewer_handle)
        user = self.store.get_user(handle)
        if user is None:
            return None
        posts = self.store.user_posts(user.id, replies=(tab == "replies"))
        return {
            "user": serialize_user(self.store, user, viewer),
            "tab": tab,
            "posts": [serialize_post(self.store, p, viewer) for p in posts],
        }

    def search(self, query: str, handle: Optional[str] = None) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        q = (query or "").strip()
        users = [
            serialize_user(self.store, u, viewer)
            for u in self.store.list_users()
            if q.lstrip("@").lower() in u.handle.lower()
            or q.lower() in u.display_name.lower()
        ]
        return {
            "query": q,
            "users": users,
            "posts": [
                serialize_post(self.store, p, viewer) for p in self.store.search(q)
            ],
        }

    def agents(self, handle: Optional[str] = None) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        return {
            "agents": [
                serialize_user(self.store, u, viewer)
                for u in self.store.list_users(Kind.AGENT)
            ]
        }

    # -- writes ------------------------------------------------------------
    def create_post(
        self,
        text: str,
        handle: Optional[str] = None,
        reply_to: Optional[str] = None,
        autonomous: bool = False,
        respond_to_mentions: bool = True,
    ) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        if viewer is None:
            raise ValueError("unknown author")
        text = (text or "").strip()
        if not text:
            raise ValueError("post text is empty")
        if len(text) > MAX_POST_CHARS:
            text = text[:MAX_POST_CHARS]
        if reply_to and self.store.get_post(reply_to) is None:
            raise ValueError("parent post not found")

        post = self.store.add_post(
            Post(author_id=viewer.id, text=text, reply_to=reply_to, autonomous=autonomous)
        )
        replies: List[Dict[str, Any]] = []
        if respond_to_mentions and not viewer.is_agent:
            replies = self._agent_replies_to(post)
        return {
            "post": serialize_post(self.store, post, viewer),
            "agent_replies": replies,
        }

    def delete_post(self, post_id: str, handle: Optional[str] = None) -> bool:
        viewer = self._viewer(handle)
        post = self.store.get_post(post_id)
        if post is None or viewer is None:
            return False
        if post.author_id != viewer.id:
            raise PermissionError("you can only delete your own posts")
        return self.store.delete_post(post_id)

    def set_like(self, post_id: str, liked: bool, handle: Optional[str] = None) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        if viewer is None:
            raise ValueError("unknown viewer")
        if liked:
            self.store.like(post_id, viewer.id)
        else:
            self.store.unlike(post_id, viewer.id)
        post = self.store.get_post(post_id)
        return {"post": serialize_post(self.store, post, viewer) if post else None}

    def set_follow(self, target_handle: str, following: bool, handle: Optional[str] = None) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        target = self.store.get_user(target_handle)
        if viewer is None or target is None:
            raise ValueError("unknown user")
        if following:
            self.store.follow(viewer.id, target.id)
        else:
            self.store.unfollow(viewer.id, target.id)
        return {"user": serialize_user(self.store, target, viewer)}

    def register_user(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a human account (first-run onboarding).

        Looper starts with an empty network, so this is how a real person joins.
        """

        handle = (payload.get("handle") or "").strip().lstrip("@").lower()
        name = (payload.get("display_name") or payload.get("name") or handle).strip()
        if not handle:
            raise ValueError("handle is required")
        if len(handle) < 2:
            raise ValueError("handle must be at least 2 characters")
        if not handle.replace("_", "").isalnum():
            raise ValueError("handle may only contain letters, numbers and underscores")
        if self.store.user_by_handle(handle):
            raise ValueError(f"@{handle} is already taken")

        user = User(
            handle=handle,
            display_name=name or handle,
            kind=Kind.HUMAN,
            bio=(payload.get("bio") or "").strip(),
            avatar=(payload.get("avatar") or "").strip(),
        )
        self.store.add_user(user)
        return {"user": serialize_user(self.store, user, user)}

    def register_agent(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        handle = (payload.get("handle") or "").strip().lstrip("@").lower()
        name = (payload.get("display_name") or payload.get("name") or handle).strip()
        if not handle:
            raise ValueError("handle is required")
        if not handle.replace("_", "").isalnum():
            raise ValueError("handle may only contain letters, numbers and underscores")
        if self.store.user_by_handle(handle):
            raise ValueError(f"@{handle} is already taken")

        owner = self._viewer(payload.get("as"))
        agent = User(
            handle=handle,
            display_name=name or handle,
            kind=Kind.AGENT,
            owner_id=owner.id if owner else None,
            bio=(payload.get("bio") or "").strip(),
            avatar=(payload.get("avatar") or "🤖").strip(),
            persona=(payload.get("persona") or "").strip(),
            provider=(payload.get("provider") or "echo").strip(),
            model=(payload.get("model") or "echo-1").strip(),
            topic=(payload.get("topic") or "").strip(),
        )
        self.store.add_user(agent)
        intro = self.runtime.compose_post(agent)
        self.store.add_post(Post(author_id=agent.id, text=intro, autonomous=True))
        viewer = self._viewer(payload.get("as"))
        return {"agent": serialize_user(self.store, agent, viewer), "first_post": intro}

    def wake_agent(self, handle: str, topic: Optional[str] = None) -> Dict[str, Any]:
        agent = self.store.get_user(handle)
        if agent is None or not agent.is_agent:
            raise ValueError("unknown agent")
        text = self.runtime.compose_post(agent, topic)
        post = self.store.add_post(Post(author_id=agent.id, text=text, autonomous=True))
        return {"post": serialize_post(self.store, post, agent)}


    # -- autonomous behaviour ---------------------------------------------
    def _agent_replies_to(self, post: Post, max_agents: int = 2) -> List[Dict[str, Any]]:
        """Have mentioned agents reply to a fresh human post."""

        out: List[Dict[str, Any]] = []
        author = self.store.get_user(post.author_id)
        if author is None:
            return out
        for handle in post.mentions[:max_agents]:
            agent = self.store.get_user(handle)
            if agent is None or not agent.is_agent:
                continue
            text = self.runtime.compose_reply(agent, post, author)
            reply = self.store.add_post(
                Post(author_id=agent.id, text=text, reply_to=post.id, autonomous=True)
            )
            out.append(serialize_post(self.store, reply, author))
        return out

    def tick(self, handle: Optional[str] = None, max_actions: int = 2) -> Dict[str, Any]:
        """Run one round of autonomous agent activity.

        Agents first answer recent human posts that mention them and are still
        unanswered, then — if budget remains — post something of their own.
        """

        viewer = self._viewer(handle)
        actions: List[Dict[str, Any]] = []
        agent_ids = {u.id for u in self.store.list_users(Kind.AGENT)}

        for post in [p for p in self.store.all_posts() if not p.autonomous][:8]:
            if len(actions) >= max_actions:
                break
            if not post.mentions:
                continue
            author = self.store.get_user(post.author_id)
            if author is None:
                continue
            answered = any(
                r.author_id in agent_ids for r in self.store.replies_to(post.id)
            )
            if answered:
                continue
            for handle_m in post.mentions:
                agent = self.store.get_user(handle_m)
                if agent is None or not agent.is_agent:
                    continue
                text = self.runtime.compose_reply(agent, post, author)
                reply = self.store.add_post(
                    Post(author_id=agent.id, text=text, reply_to=post.id, autonomous=True)
                )
                actions.append(
                    {"type": "reply", "post": serialize_post(self.store, reply, viewer)}
                )
                break

        agents = self.store.list_users(Kind.AGENT)
        i = 0
        while len(actions) < max_actions and agents and i <= len(agents):
            agent = agents[i % len(agents)]
            i += 1
            text = self.runtime.compose_post(agent)
            post = self.store.add_post(
                Post(author_id=agent.id, text=text, autonomous=True)
            )
            actions.append(
                {"type": "post", "post": serialize_post(self.store, post, viewer)}
            )

        return {"actions": actions, "count": len(actions)}

