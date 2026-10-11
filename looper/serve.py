"""Local development server for the Looper platform.

    python -m looper.serve [--port 8000] [--host 127.0.0.1]

Serves the static app (``index.html``, ``about.html``, ``assets/``) from the repo
root and routes ``/api/*`` to the platform API. The Vercel deployment uses the
serverless adapter in ``api/index.py`` instead, but both share the same code.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from .api import handle as api_handle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LooperHandler(SimpleHTTPRequestHandler):
    """Static files + the Looper API in one process."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}") or {}
        except json.JSONDecodeError:
            return {}

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api"):
            return None
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        body = self._body() if method in ("POST", "PUT", "PATCH", "DELETE") else {}
        status, payload = api_handle(method, parsed.path, query, body)
        self._json(status, payload)
        return True

    def do_GET(self) -> None:  # noqa: N802
        if self._dispatch("GET"):
            return
        if urlparse(self.path).path in ("/", ""):
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if not self._dispatch("POST"):
            self.send_error(404)

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._dispatch("DELETE"):
            self.send_error(404)

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m looper.serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    server = HTTPServer((args.host, args.port), LooperHandler)
    print(f"Looper running on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
