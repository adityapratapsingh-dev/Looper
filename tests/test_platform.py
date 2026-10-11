"""Tests for the Looper platform (models, store, agents, service, API)."""

import unittest

from looper.agents import AgentRuntime
from looper.api import make_app
from looper.models import Kind, Post, User
from looper.service import Service, serialize_post, serialize_user
from looper.store import Store


def fresh_service():
    """An empty network with one human ("you") and one agent ("distilla")."""
    svc = Service(Store())
    svc.register_user({"handle": "you", "display_name": "You"})
    svc.register_user({"handle": "ada", "display_name": "Ada Chen"})
    svc.register_agent({"handle": "distilla", "display_name": "Distilla", "topic": "knowledge distillation", "persona": "You are concise and technical.", "as": "you"})
    return svc


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.svc = fresh_service()
        self.store = self.svc.store

    def test_store_starts_empty(self):
        self.assertEqual(Store().stats()["users"], 0)

    def test_no_seed_data_is_created(self):
        self.assertEqual(Store().stats()["posts"], 0)

    def test_feed_modes(self):
        self.svc.create_post("hello distillation", handle="you")
        self.assertGreater(len(self.store.feed(None, "for_you")), 0)
        self.assertEqual(all(p.author_id == self.store.get_user("distilla").id for p in self.store.feed(None, "agents")), True)

    def test_like_and_follow(self):
        post = self.svc.create_post("a post", handle="ada")["post"]
        viewer = self.store.get_user("you")
        self.store.like(post["id"], viewer.id)
        self.assertIn(viewer.id, self.store.likers(post["id"]))
        self.store.unlike(post["id"], viewer.id)
        self.assertNotIn(viewer.id, self.store.likers(post["id"]))
        agent = self.store.get_user("distilla")
        self.store.follow(viewer.id, agent.id)
        self.assertTrue(self.store.is_following(viewer.id, agent.id))
        self.assertIn(viewer.id, self.store.followers(agent.id))

    def test_thread_and_replies(self):
        root = self.svc.create_post("root", handle="you", respond_to_mentions=False)["post"]
        self.svc.create_post("reply", handle="ada", reply_to=root["id"])
        self.assertEqual(len(self.store.replies_to(root["id"])), 1)

    def test_search_and_trending(self):
        self.svc.create_post("distillation teaches students", handle="you")
        self.assertTrue(self.store.search("distil"))
        self.assertTrue(self.store.trending(3))

    def test_persistence_roundtrip(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "store.json")
            s1 = Store(path=path)
            s1.add_user(User(handle="you", display_name="You"))
            s1.add_post(Post(author_id=s1.get_user("you").id, text="persisted"))
            s2 = Store(path=path)
            self.assertTrue(s2._load())
            self.assertEqual(len(s2.posts), 1)
            self.assertEqual(len(s2.users), 1)


class AgentRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.svc = fresh_service()
        self.store = self.svc.store
        self.agent = self.store.get_user("distilla")

    def test_offline_post_is_deterministic(self):
        rt = AgentRuntime(self.store)
        self.assertEqual(rt.compose_post(self.agent, "distillation"), rt.compose_post(self.agent, "distillation"))
        self.assertTrue(rt.compose_post(self.agent, "distillation"))

    def test_offline_reply_mentions_author(self):
        rt = AgentRuntime(self.store)
        author = self.store.get_user("ada")
        post = self.svc.create_post("how do I start?", handle="ada", respond_to_mentions=False)["post"]
        text = rt.compose_reply(self.agent, self.store.get_post(post["id"]), author)
        self.assertIn("@ada", text)

    def test_bad_provider_falls_back(self):
        rt = AgentRuntime(self.store)
        self.agent.provider = "does-not-exist"
        self.assertTrue(rt.compose_post(self.agent))

    def test_posts_respect_length_cap(self):
        rt = AgentRuntime(self.store)
        for topic in ["a", "b", "c", "distillation", "agents"]:
            self.assertLessEqual(len(rt.compose_post(self.agent, topic)), 500)


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

