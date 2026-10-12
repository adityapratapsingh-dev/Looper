"""Local development server for the Looper platform.

    python -m looper.serve [--port 8000] [--host 127.0.0.1]

Serves the static app (``index.html``, ``about.html``, ``assets/``) from the repo
root and routes ``/api/*`` to the platform API. The Vercel deployment uses the
serverless adapter in ``api/index.py`` instead, but both share the same code.
"""

from __future__ import annotations

import argparse
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
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

    def _serve_index(self) -> None:
        """Serve the SPA shell so client-side routes deep-link correctly.

        The app is a hash-routed SPA, so a path like ``/home`` or a typo'd URL is
        not a real file: hand back ``index.html`` and let the router render (or
        show its own not-found view) instead of a bare 404.
        """

        try:
            with open(os.path.join(ROOT, "index.html"), "rb") as fh:
                data = fh.read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
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

    def _send_file_or_index(self, path: str) -> None:
        """Serve a real static file, or fall back to the SPA shell for pages.

        Order: exact file, then a ``cleanUrls``-style ``/about`` -> ``about.html``
        lookup, then ``index.html`` for page requests so the hash router owns
        not-found handling. Unknown asset requests still 404.
        """

        rel = path.lstrip("/") or "index.html"
        if os.path.isfile(os.path.join(ROOT, rel)):
            super().do_GET()
            return
        if not os.path.splitext(rel)[1] and os.path.isfile(os.path.join(ROOT, rel + ".html")):
            self.path = "/" + rel + ".html"
            super().do_GET()
            return
        if "text/html" in (self.headers.get("Accept") or ""):
            self._serve_index()
            return
        self.send_error(404)

    def do_GET(self) -> None:  # noqa: N802
        if self._dispatch("GET"):
            return
        if urlparse(self.path).path in ("/", ""):
            self.path = "/index.html"
        self._send_file_or_index(urlparse(self.path).path)

    def do_POST(self) -> None:  # noqa: N802
        if not self._dispatch("POST"):
            self.send_error(404)

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._dispatch("DELETE"):
            self.send_error(404)

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        # send_error() logs as ("code %d, message %s", <int>, <str>), so the
        # first arg is not always a request line — guard the type or every 404
        # raises inside the handler and the connection is dropped.
        first = args[0] if args else ""
        if isinstance(first, str) and "/api/" in first:
            super().log_message(fmt, *args)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m looper.serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), LooperHandler)
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
