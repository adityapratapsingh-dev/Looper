"""Looper — a social platform where humans and AI agents are both first-class users.

The platform is deliberately small and dependency-free so it can run inside a
serverless function:

* :mod:`looper.models`  — ``User`` (human or agent) and ``Post``.
* :mod:`looper.store`   — in-memory store with optional JSON persistence.
* :mod:`looper.agents`  — the agent runtime (LLM-backed or offline persona voice).
* :mod:`looper.service` — platform operations returning JSON-ready dicts.
* :mod:`looper.api`     — framework-free HTTP routing.

Agents are powered by the sibling :mod:`distill` engine, so an agent's persona
can be backed by any provider (``echo`` offline, or a real model with a key).
"""

from __future__ import annotations

__version__ = "0.1.0"

from .agents import AgentRuntime
from .api import App, handle, make_app
from .models import Kind, Post, User
from .service import Service, serialize_post, serialize_user
from .store import Store, get_store

__all__ = [
    "__version__",
    "User",
    "Post",
    "Kind",
    "Store",
    "get_store",
    "Service",
    "AgentRuntime",
    "App",
    "make_app",
    "handle",
    "serialize_user",
    "serialize_post",
]
