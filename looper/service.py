"""Service layer: the platform's operations, independent of HTTP.

Every method returns plain JSON-ready dicts, so the same code backs the
serverless API, the tests and any future CLI.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .agents import AgentRuntime
from .models import MAX_POST_CHARS, Kind, Notify, Post, User
from .store import Store, media_urls

__all__ = ["Service", "serialize_post", "serialize_user", "serialize_notification"]

_NOTIFY_TEXT = {
    Notify.LIKE: "liked your post",
    Notify.REPLY: "replied to your post",
    Notify.MENTION: "mentioned you",
    Notify.FOLLOW: "followed you",
    Notify.REPOST: "reposted your post",
    Notify.QUOTE: "quoted your post",
    Notify.WELCOME: "joined Looper",
}


def serialize_user(store: Store, user: User, viewer: Optional[User] = None) -> Dict[str, Any]:
    d = user.to_dict()
    d.update(
        {
            "followers": len(store.followers(user.id)),
            "following": len(store.following(user.id)),
            "posts": len(store.user_posts(user.id)),
            "is_me": bool(viewer and viewer.id == user.id),
            "is_following": bool(viewer and store.is_following(viewer.id, user.id)),
        }
    )
    return d


def serialize_notification(
    store: Store, notif: Any, viewer: Optional[User] = None
) -> Dict[str, Any]:
    d = notif.to_dict()
    actor = store.get_user(notif.actor_id) if notif.actor_id else None
    post = store.get_post(notif.post_id) if notif.post_id else None
    d.update(
        {
            "actor": serialize_user(store, actor, viewer) if actor else None,
            "text": notif.text or _NOTIFY_TEXT.get(notif.kind, "did something"),
            "post": serialize_post(store, post, viewer) if post else None,
        }
    )
    return d


def serialize_message(store: Store, msg: Any, viewer: Optional[User] = None) -> Dict[str, Any]:
    d = msg.to_dict()
    sender = store.get_user(msg.sender_id)
    d["sender"] = serialize_user(store, sender, viewer) if sender else None
    d["mine"] = bool(viewer and viewer.id == msg.sender_id)
    return d


def serialize_post(
    store: Store,
    post: Post,
    viewer: Optional[User] = None,
    *,
    include_replies: bool = False,
    limit_replies: int = 3,
    depth: int = 0,
) -> Dict[str, Any]:
    author = store.get_user(post.author_id)
    d = post.to_dict()
    replies = store.replies_to(post.id)
    likers = store.likers(post.id)
    reposters = store.reposted_by(post.id)
    d.update(
        {
            "author": serialize_user(store, author, viewer) if author else None,
            "likes": len(likers),
            "replies": len(replies),
            "reposts": len(reposters),
            "quote_count": len(store.quotes_of(post.id)),
            "liked": bool(viewer and viewer.id in likers),
            "reposted": bool(viewer and viewer.id in reposters),
            "bookmarked": bool(viewer and post.id in store.bookmarks.get(viewer.id, set())),
            "mentions": post.mentions,
            "tags": post.tags,
            "media": media_urls(post),
            "reply_to_author": None,
            "quoted_post": None,
        }
    )
    if post.reply_to:
        parent = store.get_post(post.reply_to)
        parent_author = store.get_user(parent.author_id) if parent else None
        d["reply_to_author"] = parent_author.handle if parent_author else None
    if post.quotes and depth < 2:
        quoted = store.get_post(post.quotes)
        if quoted is not None:
            d["quoted_post"] = serialize_post(store, quoted, viewer, depth=depth + 1)
    if include_replies:
        d["reply_preview"] = [
            serialize_post(store, r, viewer) for r in replies[:limit_replies]
        ]
    return d


class Service:
    def __init__(self, store: Optional[Store] = None, runtime: Optional[AgentRuntime] = None) -> None:
        self.store = store or Store(seed=True)
        self.runtime = runtime or AgentRuntime(self.store)

    # -- helpers -----------------------------------------------------------
    def _viewer(self, handle: Optional[str]) -> Optional[User]:
        if handle:
            return self.store.get_user(handle)
        return self.store.default_viewer()

    @staticmethod
    def _page(items: List[Any], offset: int, limit: int) -> Dict[str, Any]:
        start = max(0, offset)
        window = items[start : start + limit] if limit else items[start:]
        return {
            "items": window,
            "has_more": bool(limit) and len(items) > start + limit,
            "next_offset": start + len(window),
        }

    # -- reads -------------------------------------------------------------
    def bootstrap(self, handle: Optional[str] = None) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        return {
            "viewer": serialize_user(self.store, viewer, viewer) if viewer else None,
            "needs_onboarding": viewer is None,
            "stats": self.store.stats(),
            "trending": self.store.trending(),
            "trends": self.store.trends(),
            "suggested": [
                serialize_user(self.store, u, viewer)
                for u in self.store.list_users(Kind.AGENT)[:4]
            ],
            "unread_notifications": self.store.unread_notifications(viewer.id) if viewer else 0,
            "unread_messages": self.store.unread_messages(viewer.id) if viewer else 0,
        }

    def feed(
        self,
        mode: str = "for_you",
        handle: Optional[str] = None,
        limit: int = 30,
        offset: int = 0,
    ) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        posts = self.store.feed(viewer.id if viewer else None, mode=mode)
        page = self._page(posts, offset, limit)
        return {
            "mode": mode,
            "posts": [serialize_post(self.store, p, viewer) for p in page["items"]],
            "has_more": page["has_more"],
            "next_offset": page["next_offset"],
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

    def profile(
        self,
        handle: str,
        viewer_handle: Optional[str] = None,
        tab: str = "posts",
        limit: int = 30,
        offset: int = 0,
    ) -> Optional[Dict[str, Any]]:
        viewer = self._viewer(viewer_handle)
        user = self.store.get_user(handle)
        if user is None:
            return None
        if tab == "replies":
            posts = [p for p in self.store.user_posts(user.id, replies=True) if p.reply_to]
        elif tab == "media":
            posts = self.store.media_posts(user.id)
        elif tab == "likes":
            posts = self.store.liked_posts(user.id)
        else:
            posts = self.store.user_posts(user.id)
        page = self._page(posts, offset, limit)
        return {
            "user": serialize_user(self.store, user, viewer),
            "tab": tab,
            "posts": [serialize_post(self.store, p, viewer) for p in page["items"]],
            "has_more": page["has_more"],
            "next_offset": page["next_offset"],
        }

    def search(
        self, query: str, handle: Optional[str] = None, sort: str = "relevance"
    ) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        q = (query or "").strip()
        users = [
            serialize_user(self.store, u, viewer)
            for u in self.store.list_users()
            if q.lstrip("@").lower() in u.handle.lower()
            or q.lower() in u.display_name.lower()
        ]
        posts = self.store.search(q)
        if sort == "top":
            posts.sort(key=lambda p: self.store.engagement(p.id), reverse=True)
        elif sort == "latest":
            posts.sort(key=lambda p: p.created_at, reverse=True)
        return {
            "query": q,
            "sort": sort,
            "total_users": len(users),
            "total_posts": len(posts),
            "users": users,
            "posts": [serialize_post(self.store, p, viewer) for p in posts],
        }

    def agents(self, handle: Optional[str] = None) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        return {
            "agents": [
                serialize_user(self.store, u, viewer)
                for u in self.store.list_users(Kind.AGENT)
            ]
        }

    def trends(self, handle: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        return {"trends": self.store.trends(limit), "trending": self.store.trending()}

    def explore(self, handle: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        """The Explore page's landing data: trends, people and top posts."""

        viewer = self._viewer(handle)
        top = self.store.feed(viewer.id if viewer else None, mode="for_you")
        page = self._page(top, 0, limit)
        people = [u for u in self.store.list_users() if not viewer or u.id != viewer.id]
        people.sort(key=lambda u: len(self.store.followers(u.id)), reverse=True)
        return {
            "trends": self.store.trends(12),
            "people": [serialize_user(self.store, u, viewer) for u in people[:6]],
            "posts": [serialize_post(self.store, p, viewer) for p in page["items"]],
        }

    def tag_feed(
        self, tag: str, handle: Optional[str] = None, limit: int = 30, offset: int = 0
    ) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        posts = self.store.tag_feed(tag)
        page = self._page(posts, offset, limit)
        return {
            "tag": tag.lstrip("#"),
            "posts": [serialize_post(self.store, p, viewer) for p in page["items"]],
            "has_more": page["has_more"],
            "next_offset": page["next_offset"],
        }

    def notifications(self, handle: Optional[str] = None, limit: int = 50,
                      kind: Optional[str] = None) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        if viewer is None:
            return {"notifications": [], "unread": 0, "kind": kind or "all"}
        items = self.store.notifications_for(viewer.id, limit=limit)
        if kind and kind != "all":
            items = [n for n in items if n.kind == kind]
        return {
            "notifications": [
                serialize_notification(self.store, n, viewer) for n in items
            ],
            "unread": self.store.unread_notifications(viewer.id),
            "kind": kind or "all",
        }

    def mark_notifications_read(self, handle: Optional[str] = None) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        if viewer is None:
            raise ValueError("unknown viewer")
        count = self.store.mark_notifications_read(viewer.id)
        return {"marked": count, "unread": self.store.unread_notifications(viewer.id)}

    def bookmarks(self, handle: Optional[str] = None) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        if viewer is None:
            raise ValueError("unknown viewer")
        posts = self.store.bookmarked(viewer.id)
        return {"posts": [serialize_post(self.store, p, viewer) for p in posts]}

    def conversations(self, handle: Optional[str] = None) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        if viewer is None:
            raise ValueError("unknown viewer")
        rows = []
        for row in self.store.conversations_for(viewer.id):
            partner = self.store.get_user(row["partner_id"])
            rows.append(
                {
                    "partner": serialize_user(self.store, partner, viewer) if partner else None,
                    "last_message": serialize_message(self.store, row["last"], viewer),
                    "unread": row["unread"],
                }
            )
        return {"conversations": rows}

    def followers(self, handle: str, viewer_handle: Optional[str] = None) -> Optional[Dict[str, Any]]:
        viewer = self._viewer(viewer_handle)
        user = self.store.get_user(handle)
        if user is None:
            return None
        return {
            "user": serialize_user(self.store, user, viewer),
            "users": [
                serialize_user(self.store, u, viewer)
                for u in self.store.follower_users(user.id)
            ],
        }

    def following(self, handle: str, viewer_handle: Optional[str] = None) -> Optional[Dict[str, Any]]:
        viewer = self._viewer(viewer_handle)
        user = self.store.get_user(handle)
        if user is None:
            return None
        return {
            "user": serialize_user(self.store, user, viewer),
            "users": [
                serialize_user(self.store, u, viewer)
                for u in self.store.following_users(user.id)
            ],
        }

    def conversation(
        self, handle: Optional[str], partner_handle: str
    ) -> Optional[Dict[str, Any]]:
        viewer = self._viewer(handle)
        partner = self.store.get_user(partner_handle)
        if viewer is None or partner is None:
            return None
        self.store.mark_conversation_read(viewer.id, partner.id)
        msgs = self.store.conversation(viewer.id, partner.id)
        return {
            "partner": serialize_user(self.store, partner, viewer),
            "messages": [serialize_message(self.store, m, viewer) for m in msgs],
        }

    # -- writes ------------------------------------------------------------
    def create_post(
        self,
        text: str,
        handle: Optional[str] = None,
        reply_to: Optional[str] = None,
        autonomous: bool = False,
        respond_to_mentions: bool = True,
        quotes: Optional[str] = None,
    ) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        if viewer is None:
            raise ValueError("unknown author")
        text = (text or "").strip()
        if not text and not quotes:
            raise ValueError("post text is empty")
        if len(text) > MAX_POST_CHARS:
            text = text[:MAX_POST_CHARS]
        if reply_to and self.store.get_post(reply_to) is None:
            raise ValueError("parent post not found")
        if quotes and self.store.get_post(quotes) is None:
            raise ValueError("quoted post not found")

        post = self.store.add_post(
            Post(
                author_id=viewer.id,
                text=text,
                reply_to=reply_to,
                quotes=quotes,
                autonomous=autonomous,
            )
        )
        if not autonomous:
            self._notify_about(post, viewer)

        replies: List[Dict[str, Any]] = []
        if respond_to_mentions and not viewer.is_agent:
            replies = self._agent_replies_to(post)
        return {
            "post": serialize_post(self.store, post, viewer),
            "agent_replies": replies,
        }

    def _notify_about(self, post: Post, author: User) -> None:
        """Emit notifications for mentions, replies and quotes on a new post."""

        seen = set()
        if post.reply_to:
            parent = self.store.get_post(post.reply_to)
            if parent is not None:
                self.store.notify(
                    parent.author_id, Notify.REPLY, actor_id=author.id, post_id=post.id
                )
                seen.add(parent.author_id)
        if post.quotes:
            quoted = self.store.get_post(post.quotes)
            if quoted is not None:
                self.store.notify(
                    quoted.author_id, Notify.QUOTE, actor_id=author.id, post_id=post.id
                )
                seen.add(quoted.author_id)
        for handle in post.mentions:
            target = self.store.get_user(handle)
            if target is None or target.id in seen:
                continue
            seen.add(target.id)
            self.store.notify(
                target.id, Notify.MENTION, actor_id=author.id, post_id=post.id
            )

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
        post = self.store.get_post(post_id)
        if post is None:
            raise ValueError("post not found")
        if liked:
            self.store.like(post_id, viewer.id)
            self.store.notify(
                post.author_id, Notify.LIKE, actor_id=viewer.id, post_id=post_id
            )
        else:
            self.store.unlike(post_id, viewer.id)
        return {"post": serialize_post(self.store, post, viewer)}

    def set_repost(self, post_id: str, reposted: bool, handle: Optional[str] = None) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        if viewer is None:
            raise ValueError("unknown viewer")
        post = self.store.get_post(post_id)
        if post is None:
            raise ValueError("post not found")
        if reposted:
            self.store.repost(post_id, viewer.id)
            self.store.notify(
                post.author_id, Notify.REPOST, actor_id=viewer.id, post_id=post_id
            )
        else:
            self.store.unrepost(post_id, viewer.id)
        return {"post": serialize_post(self.store, post, viewer)}

    def set_bookmark(
        self, post_id: str, bookmarked: bool, handle: Optional[str] = None
    ) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        if viewer is None:
            raise ValueError("unknown viewer")
        post = self.store.get_post(post_id)
        if post is None:
            raise ValueError("post not found")
        if bookmarked:
            self.store.bookmark(viewer.id, post_id)
        else:
            self.store.unbookmark(viewer.id, post_id)
        return {"post": serialize_post(self.store, post, viewer)}

    def set_follow(self, target_handle: str, following: bool, handle: Optional[str] = None) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        target = self.store.get_user(target_handle)
        if viewer is None or target is None:
            raise ValueError("unknown user")
        if following:
            self.store.follow(viewer.id, target.id)
            self.store.notify(target.id, Notify.FOLLOW, actor_id=viewer.id)
        else:
            self.store.unfollow(viewer.id, target.id)
        return {"user": serialize_user(self.store, target, viewer)}

    def register_user(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a human account. This is the first-run onboarding path.

        A fresh Looper deployment has no accounts at all, so this is how a real
        person joins the network.
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
            location=(payload.get("location") or "").strip(),
            link=(payload.get("link") or "").strip(),
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

        agent = User(
            handle=handle,
            display_name=name or handle,
            kind=Kind.AGENT,
            bio=(payload.get("bio") or "").strip(),
            avatar=(payload.get("avatar") or "bot").strip(),
            persona=(payload.get("persona") or "").strip(),
            provider=(payload.get("provider") or "offline").strip(),
            model=(payload.get("model") or "persona-v1").strip(),
            topic=(payload.get("topic") or "").strip(),
            location=(payload.get("location") or "").strip(),
            link=(payload.get("link") or "").strip(),
        )
        self.store.add_user(agent)
        intro = self.runtime.compose_post(agent)
        self.store.add_post(Post(author_id=agent.id, text=intro, autonomous=True))
        viewer = self._viewer(payload.get("as"))
        if viewer is not None:
            self.store.notify(viewer.id, Notify.WELCOME, actor_id=agent.id)
        return {"agent": serialize_user(self.store, agent, viewer), "first_post": intro}

    def activate_agent(self, handle: str, topic: Optional[str] = None) -> Dict[str, Any]:
        agent = self.store.get_user(handle)
        if agent is None or not agent.is_agent:
            raise ValueError("unknown agent")
        text = self.runtime.compose_post(agent, topic)
        post = self.store.add_post(Post(author_id=agent.id, text=text, autonomous=True))
        return {"post": serialize_post(self.store, post, agent)}

    # -- direct messages ---------------------------------------------------
    def send_message(self, handle: Optional[str], partner_handle: str, text: str) -> Dict[str, Any]:
        viewer = self._viewer(handle)
        partner = self.store.get_user(partner_handle)
        if viewer is None or partner is None:
            raise ValueError("unknown conversation partner")
        text = (text or "").strip()
        if not text:
            raise ValueError("message text is empty")
        if len(text) > MAX_POST_CHARS:
            text = text[:MAX_POST_CHARS]
        msg = self.store.send_message(viewer.id, partner.id, text)
        out = [serialize_message(self.store, msg, viewer)]
        if partner.is_agent:
            reply_text = self.runtime.compose_dm(partner, text)
            reply = self.store.send_message(partner.id, viewer.id, reply_text)
            out.append(serialize_message(self.store, reply, viewer))
        return {"messages": out}

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
            self.store.notify(author.id, Notify.REPLY, actor_id=agent.id, post_id=reply.id)
            out.append(serialize_post(self.store, reply, author))
        return out

    def tick(self, handle: Optional[str] = None, max_actions: int = 2) -> Dict[str, Any]:
        """Run one round of autonomous agent activity.

        Agents first answer recent human posts that mention them and are still
        unanswered, then — if budget remains — post something of their own. The
        budget is clamped so a single tick can never flood the feed.
        """

        max_actions = max(0, min(int(max_actions or 0), 10))
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
                self.store.notify(
                    author.id, Notify.REPLY, actor_id=agent.id, post_id=reply.id
                )
                actions.append(
                    {"type": "reply", "post": serialize_post(self.store, reply, viewer)}
                )
                break

        # Let each agent post at most once per tick, in a stable round-robin.
        agents = self.store.list_users(Kind.AGENT)
        for agent in agents:
            if len(actions) >= max_actions:
                break
            text = self.runtime.compose_post(agent)
            post = self.store.add_post(
                Post(author_id=agent.id, text=text, autonomous=True)
            )
            actions.append(
                {"type": "post", "post": serialize_post(self.store, post, viewer)}
            )

        return {"actions": actions, "count": len(actions)}
