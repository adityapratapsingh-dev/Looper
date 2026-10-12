"""Tests for the local dev server (looper/serve.py).

Exercises the real threaded HTTP server on an ephemeral port so the static
serving, the SPA fallback and the API routing are all covered end to end.
"""

import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from looper.serve import LooperHandler


class ServeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), LooperHandler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _get(self, path, accept=None):
        req = urllib.request.Request(self.base + path)
        if accept is not None:
            req.add_header("Accept", accept)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.headers.get("Content-Type", ""), resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers.get("Content-Type", ""), exc.read().decode("utf-8", "replace")

    def test_root_serves_the_app(self):
        status, ctype, body = self._get("/", accept="text/html")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn("Looper", body)

    def test_static_asset_is_served(self):
        status, ctype, _ = self._get("/assets/app.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", ctype)

    def test_unknown_page_falls_back_to_the_spa(self):
        # A hash-router deep link that looks like a real path must still load the
        # shell, not a 404, so the router can render it.
        status, ctype, body = self._get("/add-skill", accept="text/html")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn("Looper", body)

    def test_clean_url_serves_the_matching_page(self):
        # `/about` has no extension; it must resolve to about.html, not the SPA.
        status, ctype, body = self._get("/about", accept="text/html")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn("about", body.lower())

    def test_unknown_non_html_request_still_404s(self):
        status, _, _ = self._get("/add-skill", accept="application/json")
        self.assertEqual(status, 404)

    def test_unknown_api_route_is_json(self):
        status, ctype, body = self._get("/api/nope", accept="application/json")
        self.assertEqual(status, 404)
        self.assertIn("application/json", ctype)
        self.assertIn("no route", body)


class VercelConfigTest(unittest.TestCase):
    """Guards the deploy routing config that keeps Vercel in step with serve.py.

    These are cheap string/structure checks, but they encode hard-won facts:
    a manifest in the tree flips Vercel into backend-framework mode (everything
    routes to the function), and ``cleanUrls`` breaks the SPA fallback.
    """

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "vercel.json"), encoding="utf-8") as fh:
            cls.config = json.load(fh)

    def test_framework_is_pinned_to_null(self):
        # Without this, a committed pyproject.toml makes Vercel treat the project
        # as a Python app and route every path (even /index.html) to api/index.py.
        self.assertIsNone(self.config.get("framework"))

    def test_clean_urls_is_off(self):
        # cleanUrls rewrites index.html -> /index, which makes the SPA-fallback
        # rewrite miss and unknown paths fall through to a plain 404.
        self.assertFalse(self.config.get("cleanUrls"))

    def test_spa_fallback_and_about_rewrites_are_present(self):
        rewrites = self.config.get("rewrites", [])
        self.assertIn({"source": "/api/:path*", "destination": "/api/index"}, rewrites)
        self.assertIn({"source": "/about", "destination": "/about.html"}, rewrites)
        self.assertIn({"source": "/(.*)", "destination": "/index.html"}, rewrites)

    def test_api_path_is_rewritten_before_the_spa_fallback(self):
        sources = [r["source"] for r in self.config.get("rewrites", [])]
        self.assertLess(sources.index("/api/:path*"), sources.index("/(.*)"))


if __name__ == "__main__":
    unittest.main()
