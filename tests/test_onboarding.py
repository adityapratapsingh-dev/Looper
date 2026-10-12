"""Tests for the empty-by-default network and first-run onboarding.

Looper used to ship a seeded demo network. It now starts empty: a fresh
deployment has no accounts, and the client creates one on first visit. Seeding
is opt-in via ``Store(seed=True)`` or ``LOOPER_SEED=1``.
"""

import os
import unittest

from looper.api import make_app
from looper.service import Service
from looper.store import Store


class EmptyByDefaultTest(unittest.TestCase):
    def test_new_store_is_empty(self):
        stats = Store().stats()
        self.assertEqual(stats["users"], 0)
        self.assertEqual(stats["humans"], 0)
        self.assertEqual(stats["agents"], 0)
        self.assertEqual(stats["posts"], 0)

    def test_seed_is_still_opt_in(self):
        stats = Store(seed=True).stats()
        self.assertGreater(stats["users"], 0)
        self.assertGreater(stats["posts"], 0)

    def test_service_does_not_seed(self):
        self.assertEqual(Service(Store()).store.stats()["users"], 0)

    def test_get_store_seeds_only_with_env(self):
        import looper.store as store_module

        saved = store_module._STORE
        try:
            store_module._STORE = None
            os.environ.pop("LOOPER_SEED", None)
            os.environ["LOOPER_STORE"] = "/tmp/looper_test_empty.json"
            if os.path.exists("/tmp/looper_test_empty.json"):
                os.remove("/tmp/looper_test_empty.json")
            self.assertEqual(store_module.get_store().stats()["users"], 0)

            store_module._STORE = None
            os.environ["LOOPER_SEED"] = "1"
            self.assertGreater(store_module.get_store().stats()["users"], 0)
        finally:
            os.environ.pop("LOOPER_SEED", None)
            os.environ.pop("LOOPER_STORE", None)
            for path in ("/tmp/looper_test_empty.json",):
                if os.path.exists(path):
                    os.remove(path)
            store_module._STORE = saved


class OnboardingTest(unittest.TestCase):
    def setUp(self):
        self.app = make_app(Service(Store()))

    def test_empty_network_asks_for_onboarding(self):
        status, body = self.app.handle("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertTrue(body["needs_onboarding"])
        self.assertIsNone(body["viewer"])

    def test_register_user_then_no_onboarding(self):
        status, body = self.app.handle(
            "POST", "/api/users", body={"handle": "ada", "display_name": "Ada Chen"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["user"]["handle"], "ada")
        self.assertFalse(body["user"]["is_agent"])

        status, body = self.app.handle("GET", "/api/bootstrap", {"as": "ada"})
        self.assertFalse(body["needs_onboarding"])
        self.assertEqual(body["viewer"]["handle"], "ada")

    def test_new_account_starts_with_no_posts(self):
        self.app.handle("POST", "/api/users", body={"handle": "ada", "display_name": "Ada"})
        status, body = self.app.handle("GET", "/api/users/ada")
        self.assertEqual(body["user"]["posts"], 0)
        self.assertEqual(body["posts"], [])

    def test_handle_validation(self):
        for payload in (
            {"handle": ""},
            {"handle": "x"},
            {"handle": "bad handle"},
            {"handle": "bad!"},
        ):
            status, _ = self.app.handle("POST", "/api/users", body=payload)
            self.assertEqual(status, 400, payload)

    def test_duplicate_handle_rejected(self):
        self.app.handle("POST", "/api/users", body={"handle": "ada", "display_name": "Ada"})
        status, body = self.app.handle("POST", "/api/users", body={"handle": "ada"})
        self.assertEqual(status, 400)
        self.assertIn("taken", body["error"])

    def test_display_name_defaults_to_handle(self):
        status, body = self.app.handle("POST", "/api/users", body={"handle": "solo"})
        self.assertEqual(body["user"]["display_name"], "solo")

    def test_bio_is_optional(self):
        status, body = self.app.handle(
            "POST", "/api/users", body={"handle": "ada", "display_name": "Ada", "bio": "Hi"}
        )
        self.assertEqual(body["user"]["bio"], "Hi")

    def test_feed_is_empty_for_a_new_network(self):
        status, body = self.app.handle("GET", "/api/feed")
        self.assertEqual(status, 200)
        self.assertEqual(body["posts"], [])

    def test_first_post_after_onboarding(self):
        self.app.handle("POST", "/api/users", body={"handle": "ada", "display_name": "Ada"})
        status, body = self.app.handle("POST", "/api/posts", body={"text": "hello", "as": "ada"})
        self.assertEqual(status, 201)
        status, body = self.app.handle("GET", "/api/feed")
        self.assertEqual(len(body["posts"]), 1)
        self.assertEqual(body["posts"][0]["author"]["handle"], "ada")


if __name__ == "__main__":
    unittest.main()
