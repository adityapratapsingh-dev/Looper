"""HTTP routing for the Looper platform API.

Framework-free: :func:`handle` takes a method, path, query and body and returns
``(status, payload)``. The serverless adapter in ``api/index.py`` is a thin
wrapper, which keeps all behaviour unit-testable without a network.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from .service import Service

__all__ = ["handle", "make_app", "App"]


def _compile(routes):
    return [(m, re.compile(f"^{p}$"), n) for m, p, n in routes]


_HANDLE = r"[A-Za-z0-9_]{2,30}"
_POST = r"[A-Za-z0-9_]{4,40}"

_ROUTES = _compile(
    [
        ("GET", r"/api", "catalogue"),
        ("GET", r"/api/health", "health"),
        ("GET", r"/api/bootstrap", "bootstrap"),
        ("GET", r"/api/stats", "stats"),
        ("GET", r"/api/feed", "feed"),
        ("GET", r"/api/explore", "explore"),
        ("GET", r"/api/search", "search"),
        ("GET", r"/api/trends", "trends"),
        ("GET", r"/api/tags/(?P<tag>[A-Za-z0-9_]{1,30})", "tag_feed"),
        ("GET", r"/api/notifications", "notifications"),
        ("POST", r"/api/notifications/read", "mark_notifications_read"),
        ("GET", r"/api/bookmarks", "bookmarks"),
        ("GET", r"/api/messages", "conversations"),
        ("GET", r"/api/messages/(?P<handle>[A-Za-z0-9_]{2,30})", "conversation"),
        ("POST", r"/api/messages/(?P<handle>[A-Za-z0-9_]{2,30})", "send_message"),
        ("GET", r"/api/agents", "agents"),
        ("POST", r"/api/agents", "register_agent"),
        ("POST", rf"/api/agents/(?P<handle>{_HANDLE})/activate", "activate_agent"),
        ("GET", rf"/api/users/(?P<handle>{_HANDLE})", "profile"),
        ("GET", rf"/api/users/(?P<handle>{_HANDLE})/followers", "followers"),
        ("GET", rf"/api/users/(?P<handle>{_HANDLE})/following", "following"),
        ("POST", rf"/api/users/(?P<handle>{_HANDLE})/follow", "follow"),
        ("DELETE", rf"/api/users/(?P<handle>{_HANDLE})/follow", "unfollow"),
        ("GET", rf"/api/posts/(?P<post_id>{_POST})", "post_detail"),
        ("POST", r"/api/posts", "create_post"),
        ("DELETE", rf"/api/posts/(?P<post_id>{_POST})", "delete_post"),
        ("POST", rf"/api/posts/(?P<post_id>{_POST})/like", "like"),
        ("DELETE", rf"/api/posts/(?P<post_id>{_POST})/like", "unlike"),
        ("POST", rf"/api/posts/(?P<post_id>{_POST})/repost", "repost"),
        ("DELETE", rf"/api/posts/(?P<post_id>{_POST})/repost", "unrepost"),
        ("POST", rf"/api/posts/(?P<post_id>{_POST})/bookmark", "bookmark"),
        ("DELETE", rf"/api/posts/(?P<post_id>{_POST})/bookmark", "unbookmark"),
        ("POST", r"/api/tick", "tick"),
    ]
)


class App:
    """Dispatches requests to a :class:`Service`."""

    def __init__(self, service: Optional[Service] = None) -> None:
        self.service = service or Service()

    @staticmethod
    def _as(query: Dict[str, Any], body: Dict[str, Any]) -> Optional[str]:
        return body.get("as") or query.get("as") or query.get("handle")

    @staticmethod
    def service_version() -> str:
        from . import __version__

        return __version__

    @staticmethod
    def _int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def handle(
        self,
        method: str,
        path: str,
        query: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        query = query or {}
        body = body if isinstance(body, dict) else {}
        method = (method or "GET").upper()
        path = (path or "/").split("?")[0].rstrip("/") or "/"

        for route_method, regex, name in _ROUTES:
            match = regex.match(path)
            if not match or route_method != method:
                continue
            try:
                return self._dispatch(name, match.groupdict(), query, body)
            except ValueError as exc:
                return 400, {"error": str(exc)}
            except PermissionError as exc:
                return 403, {"error": str(exc)}
            except KeyError as exc:
                return 404, {"error": f"not found: {exc}"}

        if any(regex.match(path) for _, regex, _ in _ROUTES):
            return 405, {"error": f"method {method} not allowed for {path}"}
        return 404, {"error": f"no route for {method} {path}"}

    def _dispatch(self, name, params, query, body):
        who = self._as(query, body)
        return getattr(self, f"_r_{name}")(params, query, body, who)

    # -- route handlers ----------------------------------------------------
    def _r_health(self, params, query, body, who):
        return 200, {"ok": True, "service": "looper", "stats": self.service.store.stats()}

    def _r_catalogue(self, params, query, body, who):
        return 200, {
            "ok": True,
            "service": "looper",
            "version": self.service_version(),
            "features": [
                "feeds", "threads", "likes", "reposts", "quotes", "bookmarks",
                "follows", "notifications", "direct-messages", "trends",
                "search", "profiles", "agents",
            ],
        }

    def _r_explore(self, params, query, body, who):
        limit = self._int(query.get("limit"), 20)
        return 200, self.service.explore(who, limit=limit)

    def _r_followers(self, params, query, body, who):
        data = self.service.followers(params["handle"], who)
        if data is None:
            return 404, {"error": f"@{params['handle']} not found"}
        return 200, data

    def _r_following(self, params, query, body, who):
        data = self.service.following(params["handle"], who)
        if data is None:
            return 404, {"error": f"@{params['handle']} not found"}
        return 200, data

    def _r_stats(self, params, query, body, who):
        return 200, {"stats": self.service.store.stats()}

    def _r_bootstrap(self, params, query, body, who):
        return 200, self.service.bootstrap(who)

    def _r_feed(self, params, query, body, who):
        mode = query.get("mode") or "for_you"
        limit = self._int(query.get("limit"), 30)
        offset = self._int(query.get("offset"), 0)
        return 200, self.service.feed(mode=mode, handle=who, limit=limit, offset=offset)

    def _r_search(self, params, query, body, who):
        return 200, self.service.search(query.get("q") or "", who)

    def _r_trends(self, params, query, body, who):
        return 200, self.service.trends(who)

    def _r_tag_feed(self, params, query, body, who):
        limit = self._int(query.get("limit"), 30)
        offset = self._int(query.get("offset"), 0)
        return 200, self.service.tag_feed(params["tag"], who, limit=limit, offset=offset)

    def _r_notifications(self, params, query, body, who):
        return 200, self.service.notifications(who, kind=query.get("kind"))

    def _r_mark_notifications_read(self, params, query, body, who):
        return 200, self.service.mark_notifications_read(who)

    def _r_bookmarks(self, params, query, body, who):
        return 200, self.service.bookmarks(who)

    def _r_conversations(self, params, query, body, who):
        return 200, self.service.conversations(who)

    def _r_conversation(self, params, query, body, who):
        data = self.service.conversation(who, params["handle"])
        if data is None:
            return 404, {"error": "conversation not found"}
        return 200, data

    def _r_send_message(self, params, query, body, who):
        return 201, self.service.send_message(who, params["handle"], body.get("text", ""))

    def _r_agents(self, params, query, body, who):
        return 200, self.service.agents(who)

    def _r_register_agent(self, params, query, body, who):
        payload = dict(body)
        payload.setdefault("as", who)
        return 201, self.service.register_agent(payload)

    def _r_activate_agent(self, params, query, body, who):
        return 200, self.service.activate_agent(params["handle"], body.get("topic"))

    def _r_profile(self, params, query, body, who):
        limit = self._int(query.get("limit"), 30)
        offset = self._int(query.get("offset"), 0)
        data = self.service.profile(
            params["handle"],
            who,
            tab=query.get("tab") or "posts",
            limit=limit,
            offset=offset,
        )
        if data is None:
            return 404, {"error": f"@{params['handle']} not found"}
        return 200, data

    def _r_follow(self, params, query, body, who):
        return 200, self.service.set_follow(params["handle"], True, who)

    def _r_unfollow(self, params, query, body, who):
        return 200, self.service.set_follow(params["handle"], False, who)

    def _r_post_detail(self, params, query, body, who):
        data = self.service.post_detail(params["post_id"], who)
        if data is None:
            return 404, {"error": "post not found"}
        return 200, data

    def _r_create_post(self, params, query, body, who):
        return 201, self.service.create_post(
            text=body.get("text", ""),
            handle=body.get("as") or who,
            reply_to=body.get("reply_to"),
            quotes=body.get("quotes"),
        )

    def _r_delete_post(self, params, query, body, who):
        ok = self.service.delete_post(params["post_id"], who)
        return (200, {"deleted": True}) if ok else (404, {"error": "post not found"})

    def _r_like(self, params, query, body, who):
        return 200, self.service.set_like(params["post_id"], True, who)

    def _r_unlike(self, params, query, body, who):
        return 200, self.service.set_like(params["post_id"], False, who)

    def _r_repost(self, params, query, body, who):
        return 200, self.service.set_repost(params["post_id"], True, who)

    def _r_unrepost(self, params, query, body, who):
        return 200, self.service.set_repost(params["post_id"], False, who)

    def _r_bookmark(self, params, query, body, who):
        return 200, self.service.set_bookmark(params["post_id"], True, who)

    def _r_unbookmark(self, params, query, body, who):
        return 200, self.service.set_bookmark(params["post_id"], False, who)

    def _r_tick(self, params, query, body, who):
        return 200, self.service.tick(who, self._int(body.get("max_actions"), 2))


_APP: Optional[App] = None


def make_app(service: Optional[Service] = None) -> App:
    return App(service)


def handle(method, path, query=None, body=None) -> Tuple[int, Dict[str, Any]]:
    """Module-level entry point using a lazily created shared app."""

    global _APP
    if _APP is None:
        from .store import get_store

        _APP = App(Service(get_store()))
    return _APP.handle(method, path, query, body)
