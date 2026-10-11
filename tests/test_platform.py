"""Tests for the Looper platform (models, store, agents, service, API)."""

import unittest

from looper.agents import AgentRuntime
from looper.api import make_app
from looper.models import Kind
from looper.service import Service, serialize_post, serialize_user
from looper.store import Store


def fresh_service():
    return Service(Store(seed=True))


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(seed=True)

    def test_seed_creates_both_kinds(self):
        stats = self.store.stats()
        self.assertGreaterEqual(stats["humans"], 1)
        self.assertGreaterEqual(stats["agents"], 2)
        self.assertGreater(stats["posts"], 0)

    def test_default_viewer_is_human(self):
        self.assertEqual(self.store.default_viewer().kind, Kind.HUMAN)

    def test_feed_modes(self):
        self.assertGreater(len(self.store.feed(None, "for_you")), 0)
        self.assertGreater(len(self.store.feed(None, "agents")), 0)
        viewer = self.store.default_viewer()
        self.assertGreaterEqual(len(self.store.feed(viewer.id, "following")), 0)

    def test_like_and_follow(self):
        post = self.store.all_posts()[0]
        viewer = self.store.default_viewer()
        self.store.like(post.id, viewer.id)
        self.assertIn(viewer.id, self.store.likers(post.id))
        self.store.unlike(post.id, viewer.id)
        self.assertNotIn(viewer.id, self.store.likers(post.id))
        agent = self.store.list_users(Kind.AGENT)[0]
        self.store.follow(viewer.id, agent.id)
        self.assertTrue(self.store.is_following(viewer.id, agent.id))
        self.assertIn(viewer.id, self.store.followers(agent.id))

    def test_thread_and_replies(self):
        root = self.store.all_posts(newest_first=False)[0]
        self.assertGreaterEqual(len(self.store.thread(root.id)), 1)

    def test_search_and_trending(self):
        self.assertTrue(self.store.search("distil"))
        self.assertTrue(self.store.trending(3))

    def test_persistence_roundtrip(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "store.json")
            s1 = Store(path=path, seed=True)
            posts = len(s1.posts)
            s2 = Store(path=path, seed=False)
            self.assertTrue(s2._load())
            self.assertEqual(len(s2.posts), posts)


class AgentRuntimeTest(unittest.TestCase):
    def test_offline_post_is_deterministic(self):
        store = Store(seed=True)
        rt = AgentRuntime(store)
        agent = store.list_users(Kind.AGENT)[0]
        self.assertEqual(rt.compose_post(agent, "distillation"), rt.compose_post(agent, "distillation"))
        self.assertTrue(rt.compose_post(agent, "distillation"))

    def test_offline_reply_mentions_author(self):
        store = Store(seed=True)
        rt = AgentRuntime(store)
        agent = store.list_users(Kind.AGENT)[0]
        author = store.default_viewer()
        text = rt.compose_reply(agent, store.all_posts()[0], author)
        self.assertIn(f"@{author.handle}", text)

    def test_bad_provider_falls_back(self):
        store = Store(seed=True)
        rt = AgentRuntime(store)
        agent = store.list_users(Kind.AGENT)[0]
        agent.provider = "does-not-exist"
        self.assertTrue(rt.compose_post(agent))

    def test_posts_respect_length_cap(self):
        store = Store(seed=True)
        rt = AgentRuntime(store)
        agent = store.list_users(Kind.AGENT)[0]
        for topic in ["a", "b", "c", "distillation", "agents"]:
            self.assertLessEqual(len(rt.compose_post(agent, topic)), 500)


class ServiceTest(unittest.TestCase):
    def test_mention_triggers_agent_reply(self):
        svc = fresh_service()
        agent = svc.store.list_users(Kind.AGENT)[0]
        res = svc.create_post(f"@{agent.handle} what temperature for KD?", handle="you")
        self.assertEqual(len(res["agent_replies"]), 1)
        reply = res["agent_replies"][0]
        self.assertEqual(reply["author"]["handle"], agent.handle)
        self.assertTrue(reply["autonomous"])
        self.assertEqual(reply["reply_to"], res["post"]["id"])

    def test_no_reply_without_mention(self):
        svc = fresh_service()
        self.assertEqual(svc.create_post("just a normal post", handle="you")["agent_replies"], [])

    def test_register_agent_creates_intro_post(self):
        svc = fresh_service()
        res = svc.register_agent({"handle": "newbot", "display_name": "Newbot", "topic": "agents"})
        self.assertEqual(res["agent"]["handle"], "newbot")
        self.assertTrue(res["agent"]["is_agent"])
        self.assertTrue(res["first_post"])

    def test_duplicate_and_invalid_handles_rejected(self):
        svc = fresh_service()
        with self.assertRaises(ValueError):
            svc.register_agent({"handle": "distilla"})
        with self.assertRaises(ValueError):
            svc.register_agent({"handle": "bad handle!"})

    def test_wake_agent_creates_post(self):
        svc = fresh_service()
        self.assertTrue(svc.wake_agent("distilla")["post"]["autonomous"])

    def test_tick_runs_actions(self):
        svc = fresh_service()
        self.assertGreater(svc.tick(max_actions=2)["count"], 0)

    def test_delete_only_own_post(self):
        svc = fresh_service()
        pid = svc.create_post("mine", handle="you")["post"]["id"]
        with self.assertRaises(PermissionError):
            svc.delete_post(pid, handle="ada")
        self.assertTrue(svc.delete_post(pid, handle="you"))

    def test_serialize_flags(self):
        svc = fresh_service()
        viewer = svc.store.default_viewer()
        self.assertTrue(serialize_user(svc.store, viewer, viewer)["is_me"])
        pd = serialize_post(svc.store, svc.store.all_posts()[0], viewer)
        self.assertIn("likes", pd)
        self.assertIn("author", pd)

    def test_empty_post_rejected(self):
        svc = fresh_service()
        with self.assertRaises(ValueError):
            svc.create_post("   ", handle="you")


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.app = make_app(fresh_service())

    def test_health_and_bootstrap(self):
        status, body = self.app.handle("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        status, body = self.app.handle("GET", "/api/bootstrap")
        self.assertIn("viewer", body)
        self.assertIn("stats", body)

    def test_feed_agents_only(self):
        status, body = self.app.handle("GET", "/api/feed", {"mode": "agents"})
        self.assertEqual(status, 200)
        self.assertTrue(all(p["author"]["is_agent"] for p in body["posts"]))

    def test_create_and_like_post(self):
        status, body = self.app.handle("POST", "/api/posts", body={"text": "hello", "as": "you"})
        self.assertEqual(status, 201)
        pid = body["post"]["id"]
        status, body = self.app.handle("POST", f"/api/posts/{pid}/like", body={"as": "ada"})
        self.assertEqual(status, 200)
        self.assertTrue(body["post"]["liked"])

    def test_follow_endpoints(self):
        status, body = self.app.handle("POST", "/api/users/distilla/follow", body={"as": "you"})
        self.assertTrue(body["user"]["is_following"])
        status, body = self.app.handle("DELETE", "/api/users/distilla/follow", body={"as": "you"})
        self.assertFalse(body["user"]["is_following"])

    def test_register_agent_endpoint(self):
        status, body = self.app.handle(
            "POST", "/api/agents", body={"handle": "apibot", "display_name": "Apibot"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["agent"]["handle"], "apibot")

    def test_validation_errors(self):
        self.assertEqual(self.app.handle("POST", "/api/posts", body={"text": "", "as": "you"})[0], 400)
        self.assertEqual(self.app.handle("POST", "/api/agents", body={"handle": "distilla"})[0], 400)

    def test_unknown_route_and_method(self):
        self.assertEqual(self.app.handle("GET", "/api/nope")[0], 404)
        self.assertEqual(self.app.handle("DELETE", "/api/feed")[0], 405)

    def test_missing_profile(self):
        self.assertEqual(self.app.handle("GET", "/api/users/nobody")[0], 404)


if __name__ == "__main__":
    unittest.main()

