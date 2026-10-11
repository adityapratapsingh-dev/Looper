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


_ROUTES = _compile(
    [
        ("GET", r"/api/health", "health"),
        ("GET", r"/api/bootstrap", "bootstrap"),
        ("GET", r"/api/stats", "stats"),
        ("GET", r"/api/feed", "feed"),
        ("GET", r"/api/search", "search"),
        ("GET", r"/api/agents", "agents"),
        ("POST", r"/api/users", "register_user"),
        ("POST", r"/api/agents", "register_agent"),
        ("POST", r"/api/agents/(?P<handle>[A-Za-z0-9_]{2,30})/wake", "wake_agent"),
        ("GET", r"/api/users/(?P<handle>[A-Za-z0-9_]{2,30})", "profile"),
        ("POST", r"/api/users/(?P<handle>[A-Za-z0-9_]{2,30})/follow", "follow"),
        ("DELETE", r"/api/users/(?P<handle>[A-Za-z0-9_]{2,30})/follow", "unfollow"),
        ("GET", r"/api/posts/(?P<post_id>[A-Za-z0-9_]{4,40})", "post_detail"),
        ("POST", r"/api/posts", "create_post"),
        ("DELETE", r"/api/posts/(?P<post_id>[A-Za-z0-9_]{4,40})", "delete_post"),
        ("POST", r"/api/posts/(?P<post_id>[A-Za-z0-9_]{4,40})/like", "like"),
        ("DELETE", r"/api/posts/(?P<post_id>[A-Za-z0-9_]{4,40})/like", "unlike"),
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
        if path == "/api":
            path = "/api/health"

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

    def _r_stats(self, params, query, body, who):
        return 200, {"stats": self.service.store.stats()}

    def _r_bootstrap(self, params, query, body, who):
        return 200, self.service.bootstrap(who)

    def _r_feed(self, params, query, body, who):
        mode = query.get("mode") or "for_you"
        limit = int(query.get("limit") or 50)
        return 200, self.service.feed(mode=mode, handle=who, limit=limit)

    def _r_search(self, params, query, body, who):
        return 200, self.service.search(query.get("q") or "", who)

    def _r_agents(self, params, query, body, who):
        return 200, self.service.agents(who)

    def _r_register_user(self, params, query, body, who):
        payload = dict(body)
        payload.setdefault("as", who)
        return 201, self.service.register_user(payload)

    def _r_register_agent(self, params, query, body, who):
        payload = dict(body)
        payload.setdefault("as", who)
        return 201, self.service.register_agent(payload)

    def _r_wake_agent(self, params, query, body, who):
        return 200, self.service.wake_agent(params["handle"], body.get("topic"))

    def _r_profile(self, params, query, body, who):
        data = self.service.profile(params["handle"], who, tab=query.get("tab") or "posts")
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
        )

    def _r_delete_post(self, params, query, body, who):
        ok = self.service.delete_post(params["post_id"], who)
        return (200, {"deleted": True}) if ok else (404, {"error": "post not found"})

    def _r_like(self, params, query, body, who):
        return 200, self.service.set_like(params["post_id"], True, who)

    def _r_unlike(self, params, query, body, who):
        return 200, self.service.set_like(params["post_id"], False, who)

    def _r_tick(self, params, query, body, who):
        return 200, self.service.tick(who, int(body.get("max_actions") or 2))


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

