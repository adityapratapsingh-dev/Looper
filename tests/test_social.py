"""Tests for the richer social features: notifications, reposts, bookmarks,
direct messages, trends/hashtags, follower lists and pagination."""

import unittest

from looper.api import make_app
from looper.models import Kind
from looper.service import Service
from looper.store import Store


def fresh_service():
    return Service(Store(seed=True))


def human(store, i=0):
    return store.list_users(Kind.HUMAN)[i]


def agent(store, i=0):
    return store.list_users(Kind.AGENT)[i]


class NotificationTest(unittest.TestCase):
    def test_mention_notifies_the_mentioned_user(self):
        svc = fresh_service()
        a = agent(svc.store)
        svc.create_post(f"hey @{a.handle} thoughts?", handle="alex")
        notes = svc.notifications(a.handle)["notifications"]
        self.assertIn("mention", {n["kind"] for n in notes})

    def test_like_notifies_author(self):
        svc = fresh_service()
        post = svc.create_post("hello world", handle="maya")["post"]
        svc.set_like(post["id"], True, handle="alex")
        notes = svc.notifications("maya")["notifications"]
        self.assertTrue(any(n["kind"] == "like" for n in notes))

    def test_follow_notifies_target(self):
        svc = fresh_service()
        svc.set_follow("tempo", True, handle="alex")
        notes = svc.notifications("tempo")["notifications"]
        self.assertTrue(any(n["kind"] == "follow" for n in notes))

    def test_no_self_notification(self):
        svc = fresh_service()
        post = svc.create_post("self like", handle="alex")["post"]
        svc.set_like(post["id"], True, handle="alex")
        notes = svc.notifications("alex")["notifications"]
        self.assertFalse(any(n["kind"] == "like" for n in notes))

    def test_mark_read(self):
        svc = fresh_service()
        a = agent(svc.store)
        svc.create_post(f"@{a.handle} hi", handle="alex")
        self.assertGreater(svc.notifications(a.handle)["unread"], 0)
        res = svc.mark_notifications_read(a.handle)
        self.assertGreater(res["marked"], 0)
        self.assertEqual(res["unread"], 0)

    def test_kind_filter(self):
        svc = fresh_service()
        post = svc.create_post("filter me", handle="maya")["post"]
        svc.set_like(post["id"], True, handle="alex")
        svc.set_follow("maya", True, handle="alex")
        likes = svc.notifications("maya", kind="like")["notifications"]
        self.assertTrue(likes)
        self.assertTrue(all(n["kind"] == "like" for n in likes))


class RepostBookmarkTest(unittest.TestCase):
    def test_repost_and_unrepost(self):
        svc = fresh_service()
        post = svc.create_post("repost me", handle="maya")["post"]
        res = svc.set_repost(post["id"], True, handle="alex")
        self.assertTrue(res["post"]["reposted"])
        self.assertEqual(res["post"]["reposts"], 1)
        res = svc.set_repost(post["id"], False, handle="alex")
        self.assertFalse(res["post"]["reposted"])

    def test_bookmark_roundtrip(self):
        svc = fresh_service()
        post = svc.store.all_posts()[0]
        svc.set_bookmark(post.id, True, handle="alex")
        self.assertEqual(len(svc.bookmarks("alex")["posts"]), 1)
        svc.set_bookmark(post.id, False, handle="alex")
        self.assertEqual(len(svc.bookmarks("alex")["posts"]), 0)

    def test_quote_post_links_parent(self):
        svc = fresh_service()
        original = svc.create_post("the original", handle="maya")["post"]
        res = svc.create_post("quoting this", handle="alex", quotes=original["id"])
        self.assertEqual(res["post"]["quoted_post"]["id"], original["id"])
        detail = svc.post_detail(original["id"])
        self.assertEqual(detail["post"]["quote_count"], 1)

    def test_quote_notifies_author(self):
        svc = fresh_service()
        original = svc.create_post("the original", handle="maya")["post"]
        svc.create_post("quoting this", handle="alex", quotes=original["id"])
        notes = svc.notifications("maya")["notifications"]
        self.assertTrue(any(n["kind"] == "quote" for n in notes))


class DirectMessageTest(unittest.TestCase):
    def test_message_to_agent_gets_offline_reply(self):
        svc = fresh_service()
        a = agent(svc.store)
        res = svc.send_message("alex", a.handle, "any tips for a first 10k?")
        self.assertEqual(len(res["messages"]), 2)
        self.assertTrue(res["messages"][0]["mine"])
        self.assertFalse(res["messages"][1]["mine"])

    def test_conversation_roundtrip(self):
        svc = fresh_service()
        a = agent(svc.store)
        svc.send_message("alex", a.handle, "hello")
        convo = svc.conversation("alex", a.handle)
        self.assertEqual(convo["partner"]["handle"], a.handle)
        self.assertGreaterEqual(len(convo["messages"]), 2)

    def test_conversations_list_marks_unread(self):
        svc = fresh_service()
        a = agent(svc.store)
        svc.send_message("alex", a.handle, "hello")
        rows = svc.conversations("alex")["conversations"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["partner"]["handle"], a.handle)

    def test_empty_message_rejected(self):
        svc = fresh_service()
        with self.assertRaises(ValueError):
            svc.send_message("alex", "tempo", "   ")


class TrendAndPaginationTest(unittest.TestCase):
    def test_trends_are_hashtags(self):
        svc = fresh_service()
        svc.create_post("learning about #running today", handle="alex")
        tags = {t["tag"] for t in svc.trends()["trends"]}
        self.assertIn("running", tags)

    def test_tag_feed(self):
        svc = fresh_service()
        svc.create_post("all about #coffee", handle="alex")
        data = svc.tag_feed("coffee")
        self.assertTrue(all("coffee" in p["tags"] for p in data["posts"]))
        self.assertGreaterEqual(len(data["posts"]), 1)

    def test_feed_pagination(self):
        svc = fresh_service()
        for i in range(12):
            svc.create_post(f"post number {i}", handle="alex")
        first = svc.feed(limit=5, offset=0)
        self.assertEqual(len(first["posts"]), 5)
        self.assertTrue(first["has_more"])
        second = svc.feed(limit=5, offset=5)
        self.assertEqual(len(second["posts"]), 5)
        ids1 = {p["id"] for p in first["posts"]}
        ids2 = {p["id"] for p in second["posts"]}
        self.assertFalse(ids1 & ids2)


class ProfileTabTest(unittest.TestCase):
    def test_replies_tab_only_replies(self):
        svc = fresh_service()
        root = svc.create_post("root", handle="maya")["post"]
        svc.create_post("a reply", handle="alex", reply_to=root["id"])
        data = svc.profile("alex", tab="replies")
        self.assertTrue(all(p["reply_to"] for p in data["posts"]))

    def test_likes_tab(self):
        svc = fresh_service()
        post = svc.store.all_posts()[0]
        svc.set_like(post.id, True, handle="alex")
        data = svc.profile("alex", tab="likes")
        self.assertTrue(any(p["id"] == post.id for p in data["posts"]))

    def test_profile_pagination_slices(self):
        svc = fresh_service()
        for i in range(7):
            svc.create_post(f"mine {i}", handle="alex")
        first = svc.profile("alex", limit=3, offset=0)
        self.assertEqual(len(first["posts"]), 3)
        self.assertTrue(first["has_more"])
        second = svc.profile("alex", limit=3, offset=3)
        self.assertEqual(len(second["posts"]), 3)
        self.assertFalse(
            {p["id"] for p in first["posts"]} & {p["id"] for p in second["posts"]}
        )

    def test_tag_pagination_slices(self):
        svc = fresh_service()
        for i in range(5):
            svc.create_post(f"tagged {i} #looper", handle="alex")
        first = svc.tag_feed("looper", limit=2, offset=0)
        self.assertEqual(len(first["posts"]), 2)
        self.assertTrue(first["has_more"])
        rest = svc.tag_feed("looper", limit=2, offset=4)
        self.assertTrue(rest["posts"])
        self.assertEqual(len(rest["posts"]), 1)
        self.assertFalse(rest["has_more"])


class FollowListTest(unittest.TestCase):
    def test_followers_and_following_lists(self):
        svc = fresh_service()
        svc.set_follow("tempo", True, handle="alex")
        following = svc.following("alex")["users"]
        self.assertIn("tempo", {u["handle"] for u in following})
        followers = svc.followers("tempo")["users"]
        self.assertIn("alex", {u["handle"] for u in followers})

    def test_unknown_user_returns_none(self):
        svc = fresh_service()
        self.assertIsNone(svc.followers("nobody"))
        self.assertIsNone(svc.following("nobody"))


class NewApiRoutesTest(unittest.TestCase):
    def setUp(self):
        self.app = make_app(fresh_service())

    def test_catalogue_route(self):
        status, body = self.app.handle("GET", "/api")
        self.assertEqual(status, 200)
        self.assertIn("features", body)

    def test_distill_route_is_gone(self):
        status, _ = self.app.handle("POST", "/api/distill", body={"prompts": "hi"})
        self.assertEqual(status, 404)

    def test_notifications_routes(self):
        status, body = self.app.handle("GET", "/api/notifications", {"as": "alex"})
        self.assertEqual(status, 200)
        self.assertIn("notifications", body)

    def test_messages_routes(self):
        status, body = self.app.handle(
            "POST", "/api/messages/tempo", {"as": "alex"}, {"text": "hello"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(len(body["messages"]), 2)
        status, body = self.app.handle("GET", "/api/messages", {"as": "alex"})
        self.assertEqual(len(body["conversations"]), 1)

    def test_repost_and_bookmark_routes(self):
        _, created = self.app.handle(
            "POST", "/api/posts", body={"text": "x", "as": "alex"}
        )
        pid = created["post"]["id"]
        status, body = self.app.handle(
            "POST", f"/api/posts/{pid}/repost", body={"as": "maya"}
        )
        self.assertTrue(body["post"]["reposted"])
        status, body = self.app.handle(
            "POST", f"/api/posts/{pid}/bookmark", body={"as": "maya"}
        )
        self.assertTrue(body["post"]["bookmarked"])

    def test_trends_and_tags_routes(self):
        self.app.handle("POST", "/api/posts", body={"text": "a #tagged post", "as": "alex"})
        status, body = self.app.handle("GET", "/api/trends")
        self.assertIn("trends", body)
        status, body = self.app.handle("GET", "/api/tags/tagged")
        self.assertEqual(body["tag"], "tagged")

    def test_explore_and_follow_routes(self):
        status, body = self.app.handle("GET", "/api/explore", {"as": "alex"})
        self.assertEqual(status, 200)
        self.assertIn("people", body)
        status, body = self.app.handle("GET", "/api/users/alex/following")
        self.assertEqual(status, 200)
        self.assertIn("users", body)


if __name__ == "__main__":
    unittest.main()
