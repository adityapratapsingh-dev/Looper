"""Vercel serverless function — a live demo of the Looper distillation framework.

Routes (Vercel maps ``api/demo.py`` to ``/api/demo``):

* ``GET  /api/demo``  -> framework metadata (modes, providers, filters, formatters)
* ``POST /api/demo``  -> runs the real ``data`` distillation mode offline using the
  built-in ``echo`` teacher (no API keys required) and returns the generated
  training records.

The handler imports the ``distill`` package that lives at the repository root.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

# Make the repo root importable (the framework package lives next to /api).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from distill import __version__  # noqa: E402
from distill.modes import get_mode  # noqa: E402
from distill.registry import FILTERS, FORMATTERS, MODES, PROVIDERS  # noqa: E402

_MAX_PROMPTS = 25
_MAX_PROMPT_CHARS = 2000


def _catalogue() -> dict:
    import distill.data  # noqa: F401  (self-register filters/formatters)
    import distill.modes  # noqa: F401
    import distill.providers  # noqa: F401

    return {
        "name": "Looper",
        "version": __version__,
        "modes": MODES.names(),
        "providers": PROVIDERS.names(),
        "filters": FILTERS.names(),
        "formatters": FORMATTERS.names(),
    }


def _run_demo(payload: dict) -> dict:
    """Run the real `data` mode offline and return its output records + stats."""

    import tempfile

    from distill.agent.trajectory import read_jsonl

    prompts = payload.get("prompts") or []
    if isinstance(prompts, str):
        prompts = [line.strip() for line in prompts.splitlines() if line.strip()]
    prompts = [str(p)[:_MAX_PROMPT_CHARS] for p in prompts][:_MAX_PROMPTS]
    if not prompts:
        raise ValueError("provide at least one prompt")

    fmt = payload.get("format") or "chat"
    if fmt not in FORMATTERS.names():
        fmt = "chat"

    filters = payload.get("filters")
    if not isinstance(filters, list) or not filters:
        filters = [
            {"name": "non_empty"},
            {"name": "length", "min_chars": 8, "max_chars": 4000},
            {"name": "banned_substrings", "substrings": ["as an ai language model"]},
        ]

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
            "filters": filters,
            "dedupe": {"exact": True, "near": {"enabled": True, "threshold": 0.9}},
            "format": fmt,
            "output": out,
        }
        result = get_mode("data")(cfg).run()
        records = read_jsonl(out)

    return {"result": result.to_dict(), "records": records}


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:  # noqa: N802 - http.server API
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._send(200, _catalogue())
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("body must be a JSON object")
            self._send(200, _run_demo(payload))
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})
