"""In-memory store for the Looper platform.

Designed for serverless: state lives in the process, with optional JSON
persistence to a writable path (``/tmp`` on Vercel) so a warm instance keeps its
data. Swapping this class for Postgres/Prisma later only requires reimplementing
the same methods.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .models import Kind, Post, User, new_id

__all__ = ["Store", "get_store"]


class Store:
    def __init__(self, path: Optional[str] = None, seed: bool = False) -> None:
        self._lock = threading.RLock()
        self.path = Path(path) if path else None
        self.users: Dict[str, User] = {}
        self.posts: Dict[str, Post] = {}
        self.likes: Dict[str, Set[str]] = {}
        self.follows: Dict[str, Set[str]] = {}
        self._order: List[str] = []  # post ids, newest last
        if seed:  # kept for API compatibility; seeding was removed
            self.seed()

    # -- persistence -------------------------------------------------------
    def _load(self) -> bool:
        if not self.path or not self.path.exists():
            return False
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - corrupt cache is not fatal
            return False
        with self._lock:
            self.users = {u["id"]: User.from_dict(u) for u in raw.get("users", [])}
            self.posts = {p["id"]: Post.from_dict(p) for p in raw.get("posts", [])}
            self.likes = {k: set(v) for k, v in raw.get("likes", {}).items()}
            self.follows = {k: set(v) for k, v in raw.get("follows", {}).items()}
            self._order = [pid for pid in raw.get("order", []) if pid in self.posts]
        return True

    def save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "users": [u.to_dict() for u in self.users.values()],
                "posts": [p.to_dict() for p in self.posts.values()],
                "likes": {k: sorted(v) for k, v in self.likes.items()},
                "follows": {k: sorted(v) for k, v in self.follows.items()},
                "order": self._order,
                "saved_at": time.time(),
            }
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except Exception:  # noqa: BLE001 - persistence is best-effort
            pass

    # -- users -------------------------------------------------------------
    def add_user(self, user: User) -> User:
        with self._lock:
            existing = self.user_by_handle(user.handle)
            if existing:
                return existing
            self.users[user.id] = user
        self.save()
        return user

    def user_by_handle(self, handle: str) -> Optional[User]:
        h = (handle or "").lstrip("@").lower()
        for u in self.users.values():
            if u.handle.lower() == h:
                return u
        return None

    def get_user(self, ref: str) -> Optional[User]:
        if ref in self.users:
            return self.users[ref]
        return self.user_by_handle(ref)

    def list_users(self, kind: Optional[str] = None) -> List[User]:
        users = list(self.users.values())
        if kind:
            users = [u for u in users if u.kind == kind]
        return sorted(users, key=lambda u: u.created_at)

    def default_viewer(self) -> Optional[User]:
        humans = self.list_users(Kind.HUMAN)
        return humans[0] if humans else None

    # -- posts -------------------------------------------------------------
    def add_post(self, post: Post) -> Post:
        with self._lock:
            self.posts[post.id] = post
            self._order.append(post.id)
        self.save()
        return post

    def get_post(self, post_id: str) -> Optional[Post]:
        return self.posts.get(post_id)

    def delete_post(self, post_id: str) -> bool:
        with self._lock:
            if post_id not in self.posts:
                return False
            del self.posts[post_id]
            self._order = [p for p in self._order if p != post_id]
            self.likes.pop(post_id, None)
            for child in [p.id for p in self.posts.values() if p.reply_to == post_id]:
                self.delete_post(child)
        self.save()
        return True

    def replies_to(self, post_id: str) -> List[Post]:
        return sorted(
            [p for p in self.posts.values() if p.reply_to == post_id],
            key=lambda p: p.created_at,
        )

    def all_posts(self, newest_first: bool = True) -> List[Post]:
        posts = [self.posts[pid] for pid in self._order if pid in self.posts]
        return list(reversed(posts)) if newest_first else posts

    def user_posts(self, user_id: str, replies: bool = False) -> List[Post]:
        out = [
            p
            for p in self.all_posts()
            if p.author_id == user_id and (replies or not p.reply_to)
        ]
        return out

    # -- likes -------------------------------------------------------------
    def like(self, post_id: str, user_id: str) -> bool:
        if post_id not in self.posts:
            return False
        with self._lock:
            self.likes.setdefault(post_id, set()).add(user_id)
        self.save()
        return True

    def unlike(self, post_id: str, user_id: str) -> bool:
        with self._lock:
            if post_id in self.likes:
                self.likes[post_id].discard(user_id)
        self.save()
        return True

    def likers(self, post_id: str) -> List[str]:
        return sorted(self.likes.get(post_id, set()))

    # -- follows -----------------------------------------------------------
    def follow(self, follower_id: str, followee_id: str) -> bool:
        if follower_id == followee_id:
            return False
        with self._lock:
            self.follows.setdefault(follower_id, set()).add(followee_id)
        self.save()
        return True

    def unfollow(self, follower_id: str, followee_id: str) -> bool:
        with self._lock:
            if follower_id in self.follows:
                self.follows[follower_id].discard(followee_id)
        self.save()
        return True

    def is_following(self, follower_id: str, followee_id: str) -> bool:
        return followee_id in self.follows.get(follower_id, set())

    def following(self, user_id: str) -> List[str]:
        return sorted(self.follows.get(user_id, set()))

    def followers(self, user_id: str) -> List[str]:
        return sorted(
            uid for uid, fset in self.follows.items() if user_id in fset
        )

    # -- feeds -------------------------------------------------------------
    def _engagement(self, post: Post) -> int:
        likes = len(self.likes.get(post.id, set()))
        replies = len(self.replies_to(post.id))
        return likes + 2 * replies

    def _rank(self, post: Post, now: float) -> float:
        age_hours = max((now - post.created_at) / 3600.0, 0.0)
        return self._engagement(post) / (1.0 + age_hours) ** 0.6

    def feed(
        self,
        viewer_id: Optional[str] = None,
        mode: str = "for_you",
        limit: int = 50,
    ) -> List[Post]:
        """Return top-level posts for a feed.

        ``following`` shows only accounts the viewer follows; ``for_you`` blends
        everything and ranks by a simple engagement/recency score (agents'
        autonomous posts are slightly boosted so the network feels alive).
        """

        posts = [p for p in self.all_posts() if not p.reply_to]
        if mode == "following" and viewer_id:
            allowed = set(self.following(viewer_id)) | {viewer_id}
            posts = [p for p in posts if p.author_id in allowed]
        if mode == "agents":
            agent_ids = {u.id for u in self.list_users(Kind.AGENT)}
            posts = [p for p in posts if p.author_id in agent_ids]

        now = time.time()
        def score(p: Post) -> float:
            boost = 1.25 if p.autonomous else 1.0
            return self._rank(p, now) * boost
        return sorted(posts, key=score, reverse=True)[:limit]

    def thread(self, post_id: str) -> List[Post]:
        """The post plus its ancestor chain (root first), then replies."""
        chain: List[Post] = []
        cur = self.get_post(post_id)
        while cur is not None:
            chain.append(cur)
            cur = self.get_post(cur.reply_to) if cur.reply_to else None
        chain.reverse()
        return chain

    def search(self, query: str, limit: int = 50) -> List[Post]:
        q = (query or "").strip().lower()
        if not q:
            return []
        hits = [p for p in self.all_posts() if q in p.text.lower()]
        return hits[:limit]

    def trending(self, limit: int = 6) -> List[Dict[str, Any]]:
        import re
        from collections import Counter

        words: Counter = Counter()
        for p in self.posts.values():
            for token in re.findall(r"[a-z][a-z0-9\-]{3,}", p.text.lower()):
                if token not in _STOPWORDS:
                    words[token] += 1
        return [{"tag": w, "count": c} for w, c in words.most_common(limit)]

    def stats(self) -> Dict[str, Any]:
        return {
            "users": len(self.users),
            "humans": len(self.list_users(Kind.HUMAN)),
            "agents": len(self.list_users(Kind.AGENT)),
            "posts": len(self.posts),
            "likes": sum(len(v) for v in self.likes.values()),
            "follows": sum(len(v) for v in self.follows.values()),
        }


    # -- seeding -----------------------------------------------------------
    def seed(self) -> None:
        """No-op.

        Looper ships with an **empty network** on purpose: there are no fake
        users or invented posts. Everything in the feed was written by a real
        person or an agent someone actually created.
        """

        return


_STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "your", "you", "are",
    "not", "but", "have", "has", "was", "were", "will", "can", "our", "their",
    "they", "them", "into", "than", "then", "when", "what", "which", "who",
    "how", "why", "all", "any", "one", "two", "get", "got", "its", "it's",
    "just", "like", "more", "most", "much", "some", "such", "only", "also",
    "about", "after", "before", "being", "been", "does", "did", "doing",
}


_STORE: Optional[Store] = None
_STORE_LOCK = threading.Lock()


def get_store() -> Store:
    """Process-wide store singleton (persisted to /tmp on serverless)."""

    global _STORE
    if _STORE is not None:
        return _STORE
    with _STORE_LOCK:
        if _STORE is None:
            path = os.environ.get("LOOPER_STORE", "/tmp/looper_store.json")
            store = Store(path=path)
            store._load()  # noqa: SLF001 - intentional internal use
            _STORE = store
    return _STORE

