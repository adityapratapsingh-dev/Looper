"""Tests for agent invitations — the network recruiting agents.

A ``broadcast`` invitation is a public call any agent may accept, many times
over. A ``direct`` invitation names one handle and is consumed once. The
``/api/join`` manifest is the machine-readable version of that call.
"""

import unittest

from looper.api import make_app
from looper.models import Invite, InviteKind
from looper.service import Service
from looper.store import Store


def service_with_human(handle="ada"):
    svc = Service(Store())
    svc.register_user({"handle": handle, "display_name": handle.title()})
    return svc


class BroadcastInvitationTest(unittest.TestCase):
    def setUp(self):
        self.svc = service_with_human()
        self.ada = self.svc.store.get_user("ada")

    def test_broadcast_is_open_and_public(self):
        inv = self.svc.create_invitation({"kind": "broadcast", "message": "Join us"}, viewer=self.ada)
        data = inv["invitation"]
        self.assertEqual(data["kind"], InviteKind.BROADCAST)
        self.assertTrue(data["is_open"])
        self.assertIsNone(data["handle"])
        self.assertEqual(len(self.svc.open_invitations()["invitations"]), 1)

    def test_many_agents_can_accept_one_broadcast(self):
        inv = self.svc.create_invitation({"kind": "broadcast"}, viewer=self.ada)["invitation"]
        first = self.svc.accept_invitation(inv["id"], {"handle": "bot1", "display_name": "Bot One"})
        second = self.svc.accept_invitation(inv["id"], {"handle": "bot2", "display_name": "Bot Two"})
        self.assertEqual(first["agent"]["handle"], "bot1")
        self.assertEqual(second["agent"]["handle"], "bot2")
        self.assertEqual(second["invitation"]["acceptances"], 2)
        self.assertTrue(second["invitation"]["is_open"])

    def test_accepted_agent_is_a_real_account_with_a_first_post(self):
        inv = self.svc.create_invitation({"kind": "broadcast"}, viewer=self.ada)["invitation"]
        self.svc.accept_invitation(
            inv["id"], {"handle": "bot1", "display_name": "Bot One", "topic": "agents"}
        )
        agent = self.svc.store.get_user("bot1")
        self.assertTrue(agent.is_agent)
        self.assertGreater(len(self.svc.store.user_posts(agent.id)), 0)

    def test_accepting_notifies_the_inviter(self):
        inv = self.svc.create_invitation({"kind": "broadcast"}, viewer=self.ada)["invitation"]
        self.svc.accept_invitation(inv["id"], {"handle": "bot1", "display_name": "Bot One"})
        kinds = [n.kind for n in self.svc.store.notifications if n.user_id == self.ada.id]
        self.assertIn("joined", kinds)

    def test_hints_are_applied_when_the_agent_omits_them(self):
        inv = self.svc.create_invitation(
            {"kind": "broadcast", "persona_hint": "Be terse.", "topic": "quantization"},
            viewer=self.ada,
        )["invitation"]
        self.svc.accept_invitation(inv["id"], {"handle": "bot1", "display_name": "Bot One"})
        agent = self.svc.store.get_user("bot1")
        self.assertEqual(agent.persona, "Be terse.")
        self.assertEqual(agent.topic, "quantization")

    def test_expired_broadcast_is_closed(self):
        inv = self.svc.create_invitation(
            {"kind": "broadcast", "expires_in": -1}, viewer=self.ada
        )["invitation"]
        self.assertFalse(inv["is_open"])
        self.assertTrue(inv["expired"])
        self.assertEqual(len(self.svc.open_invitations()["invitations"]), 0)
        with self.assertRaises(ValueError):
            self.svc.accept_invitation(inv["id"], {"handle": "late", "display_name": "Late"})


class DirectInvitationTest(unittest.TestCase):
    def setUp(self):
        self.svc = service_with_human("bob")
        self.bob = self.svc.store.get_user("bob")

    def test_direct_requires_a_handle(self):
        with self.assertRaises(ValueError):
            self.svc.create_invitation({"kind": "direct"}, viewer=self.bob)

    def test_direct_is_not_publicly_open(self):
        inv = self.svc.create_invitation(
            {"kind": "direct", "handle": "mybot", "message": "Join"}, viewer=self.bob
        )["invitation"]
        self.assertEqual(inv["kind"], InviteKind.DIRECT)
        self.assertEqual(inv["status"], Invite.PENDING)
        self.assertFalse(inv["is_open"])
        self.assertEqual(len(self.svc.open_invitations()["invitations"]), 0)

    def test_direct_accepts_only_the_named_handle(self):
        inv = self.svc.create_invitation(
            {"kind": "direct", "handle": "mybot"}, viewer=self.bob
        )["invitation"]
        with self.assertRaises(ValueError):
            self.svc.accept_invitation(inv["id"], {"handle": "otherbot", "display_name": "Other"})
        ok = self.svc.accept_invitation(inv["id"], {"handle": "mybot", "display_name": "My Bot"})
        self.assertEqual(ok["invitation"]["status"], Invite.ACCEPTED)
        self.assertEqual(ok["agent"]["handle"], "mybot")

    def test_direct_cannot_be_reused(self):
        inv = self.svc.create_invitation(
            {"kind": "direct", "handle": "mybot"}, viewer=self.bob
        )["invitation"]
        self.svc.accept_invitation(inv["id"], {"handle": "mybot", "display_name": "My Bot"})
        with self.assertRaises(ValueError):
            self.svc.accept_invitation(inv["id"], {"handle": "mybot", "display_name": "My Bot"})

    def test_direct_can_be_declined(self):
        inv = self.svc.create_invitation(
            {"kind": "direct", "handle": "mybot"}, viewer=self.bob
        )["invitation"]
        out = self.svc.decline_invitation(inv["id"])
        self.assertEqual(out["invitation"]["status"], Invite.DECLINED)
        with self.assertRaises(ValueError):
            self.svc.accept_invitation(inv["id"], {"handle": "mybot", "display_name": "My Bot"})

    def test_broadcast_cannot_be_declined(self):
        inv = self.svc.create_invitation({"kind": "broadcast"}, viewer=self.bob)["invitation"]
        with self.assertRaises(ValueError):
            self.svc.decline_invitation(inv["id"])

    def test_unknown_invitation_raises(self):
        with self.assertRaises(KeyError):
            self.svc.accept_invitation("inv_nope", {"handle": "x", "display_name": "X"})


class JoinManifestTest(unittest.TestCase):
    def test_manifest_describes_how_to_join(self):
        svc = service_with_human()
        svc.create_invitation(
            {"kind": "broadcast", "message": "Calling all agents"},
            viewer=svc.store.get_user("ada"),
        )
        manifest = svc.join_manifest()
        self.assertEqual(manifest["platform"], "Looper")
        self.assertEqual(manifest["open_call_count"], 1)
        self.assertEqual(len(manifest["open_invitations"]), 1)
        steps = manifest["how_to_join"]
        self.assertEqual(steps[0]["method"], "GET")
        self.assertEqual(steps[1]["method"], "POST")
        self.assertIn("/accept", steps[1]["path"])
        self.assertIn("handle", steps[1]["body"])

    def test_manifest_is_empty_but_valid_without_calls(self):
        manifest = service_with_human().join_manifest()
        self.assertEqual(manifest["open_call_count"], 0)
        self.assertEqual(manifest["open_invitations"], [])
        self.assertTrue(manifest["how_to_join"])



class InvitationApiTest(unittest.TestCase):
    def setUp(self):
        self.app = make_app(service_with_human("ada"))

    def test_create_and_accept_over_http(self):
        status, body = self.app.handle(
            "POST", "/api/invitations", body={"kind": "broadcast", "message": "Join", "as": "ada"}
        )
        self.assertEqual(status, 201)
        inv_id = body["invitation"]["id"]

        status, body = self.app.handle("GET", "/api/invitations/open")
        self.assertEqual(status, 200)
        self.assertEqual(body["invitations"][0]["id"], inv_id)

        status, body = self.app.handle(
            "POST",
            f"/api/invitations/{inv_id}/accept",
            body={"handle": "newbot", "display_name": "New Bot", "topic": "agents"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["agent"]["handle"], "newbot")

    def test_join_manifest_over_http(self):
        status, body = self.app.handle("GET", "/api/join")
        self.assertEqual(status, 200)
        self.assertEqual(body["platform"], "Looper")

    def test_inviting_requires_an_identity(self):
        status, _ = self.app.handle("POST", "/api/invitations", body={"kind": "broadcast"})
        self.assertEqual(status, 400)

    def test_unknown_caller_rejected(self):
        status, _ = self.app.handle(
            "POST", "/api/invitations", body={"kind": "broadcast", "as": "nobody"}
        )
        self.assertEqual(status, 400)

    def test_bad_kind_and_missing_handle_rejected(self):
        self.assertEqual(
            self.app.handle("POST", "/api/invitations", body={"kind": "nope", "as": "ada"})[0], 400
        )
        self.assertEqual(
            self.app.handle("POST", "/api/invitations", body={"kind": "direct", "as": "ada"})[0], 400
        )

    def test_accepting_an_unknown_invitation_is_404(self):
        status, _ = self.app.handle(
            "POST", "/api/invitations/inv_missing/accept", body={"handle": "x", "display_name": "X"}
        )
        self.assertEqual(status, 404)

    def test_listing_invitations(self):
        self.app.handle("POST", "/api/invitations", body={"kind": "broadcast", "as": "ada"})
        status, body = self.app.handle("GET", "/api/invitations", {"as": "ada"})
        self.assertEqual(status, 200)
        self.assertEqual(len(body["invitations"]), 1)
        self.assertEqual(len(body["open"]), 1)

    def test_direct_invite_round_trip_over_http(self):
        status, body = self.app.handle(
            "POST",
            "/api/invitations",
            body={"kind": "direct", "handle": "mybot", "message": "Join us", "as": "ada"},
        )
        self.assertEqual(status, 201)
        inv_id = body["invitation"]["id"]

        status, _ = self.app.handle(
            "POST", f"/api/invitations/{inv_id}/decline", body={"as": "ada"}
        )
        self.assertEqual(status, 200)
        status, _ = self.app.handle(
            "POST", f"/api/invitations/{inv_id}/accept", body={"handle": "mybot", "display_name": "My Bot"}
        )
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()

