"""Vercel serverless entrypoint for the Looper platform.

Routes (all JSON):

* ``/api/*``            — the social platform API (see ``looper.api``)
* ``POST /api/distill`` — runs the real ``distill`` framework's ``data`` mode
  (the engine that powers agents), returning the training records it produces.

The handler is a thin adapter: all logic lives in the ``looper`` package so it
can be unit-tested without HTTP.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from looper.api import handle as platform_handle  # noqa: E402

_MAX_BODY = 64 * 1024


def _distill(payload: dict) -> tuple:
    """Run the distillation engine (offline echo teacher) and return records."""

    import tempfile

    from distill.agent.trajectory import read_jsonl
    from distill.modes import get_mode
    from distill.registry import FORMATTERS

    prompts = payload.get("prompts") or []
    if isinstance(prompts, str):
        prompts = [line.strip() for line in prompts.splitlines() if line.strip()]
    prompts = [str(p)[:2000] for p in prompts][:25]
    if not prompts:
        return 400, {"error": "provide at least one prompt"}

    fmt = payload.get("format") or "chat"
    if fmt not in FORMATTERS.names():
        fmt = "chat"

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "data.jsonl")
        cfg = {
            "mode": "data",
            "teacher": {"provider": "echo", "model": "echo-1"},
            "prompts": prompts,
            "sampling": {
                "temperature": float(payload.get("temperature", 0.8)),
                "max_tokens": 128,
            },
            "filters": [
                {"name": "non_empty"},
                {"name": "length", "min_chars": 8, "max_chars": 4000},
                {"name": "banned_substrings", "substrings": ["as an ai language model"]},
            ],
            "dedupe": {"exact": True, "near": {"enabled": True, "threshold": 0.9}},
            "format": fmt,
            "output": out,
        }
        result = get_mode("data")(cfg).run()
        records = read_jsonl(out)

    return 200, {"result": result.to_dict(), "records": records}


class handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # -- plumbing ----------------------------------------------------------
    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, _MAX_BODY))
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON body: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("body must be a JSON object")
        return payload

    # -- verbs -------------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._route("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._route("POST")

    def do_DELETE(self) -> None:  # noqa: N802
        self._route("DELETE")

    def _route(self, method: str) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            body = self._read_body() if method in ("POST", "PUT", "PATCH") else {}

            if path.rstrip("/") == "/api/distill" and method == "POST":
                status, payload = _distill(body)
                return self._send(status, payload)

            status, payload = platform_handle(method, path, query, body)
            self._send(status, payload)
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})
