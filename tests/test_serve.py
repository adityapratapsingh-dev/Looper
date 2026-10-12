"""Tests for the local dev server (looper/serve.py).

Exercises the real threaded HTTP server on an ephemeral port so the static
serving, the SPA fallback and the API routing are all covered end to end.
"""

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


if __name__ == "__main__":
    unittest.main()
