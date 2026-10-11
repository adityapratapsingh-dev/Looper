"""Tests for providers (echo + conversions)."""

import unittest

from distill.providers import get_provider
from distill.types import ChatMessage, Role, SamplingParams, ToolSpec


class EchoProviderTest(unittest.TestCase):
    def setUp(self):
        self.p = get_provider("echo")

    def test_basic_chat(self):
        c = self.p.chat([ChatMessage.user("hello world")])
        self.assertIn("hello world", c.text)
        self.assertEqual(c.provider, "echo")
        self.assertGreater(c.usage.total_tokens, 0)

    def test_deterministic(self):
        a = self.p.chat([ChatMessage.user("same")]).text
        b = self.p.chat([ChatMessage.user("same")]).text
        self.assertEqual(a, b)

    def test_tool_call_emitted(self):
        spec = ToolSpec("search", "search", {"type": "object", "properties": {"query": {"type": "string"}}})
        c = self.p.chat([ChatMessage.user("please search for cats")], tools=[spec])
        self.assertTrue(c.message.tool_calls)
        self.assertEqual(c.message.tool_calls[0].name, "search")
        self.assertEqual(c.finish_reason, "tool_calls")

    def test_no_tool_after_tool_result(self):
        spec = ToolSpec("search", "search", {"type": "object", "properties": {}})
        messages = [
            ChatMessage.user("search cats"),
            ChatMessage.assistant("", tool_calls=[__import__("distill").ToolCall("search", {})]),
            ChatMessage.tool("result", "call_1"),
        ]
        c = self.p.chat(messages, tools=[spec])
        self.assertFalse(c.message.tool_calls)

    def test_logprobs(self):
        c = self.p.chat(
            [ChatMessage.user("hello there")],
            params=SamplingParams(logprobs=True, top_logprobs=3),
        )
        self.assertTrue(c.logprobs)
        self.assertTrue(c.logprobs[0].top_logprobs)

    def test_no_logprobs_by_default(self):
        c = self.p.chat([ChatMessage.user("hi")])
        self.assertEqual(c.logprobs, [])

    def test_white_box_distribution_sums_to_one(self):
        dist = self.p.next_token_distribution([ChatMessage.user("hi")])
        self.assertAlmostEqual(sum(dist.values()), 1.0, places=6)


class MessageConversionTest(unittest.TestCase):
    def test_openai_tool_message(self):
        from distill.providers.openai_compat import _to_openai_messages

        msgs = [
            ChatMessage.system("sys"),
            ChatMessage.user("hi"),
            ChatMessage.tool("42", tool_call_id="call_1", name="calc"),
        ]
        out = _to_openai_messages(msgs)
        self.assertEqual(out[0], {"role": "system", "content": "sys"})
        self.assertEqual(out[2]["role"], "tool")
        self.assertEqual(out[2]["tool_call_id"], "call_1")

    def test_openai_assistant_tool_calls(self):
        from distill.providers.openai_compat import _to_openai_messages
        from distill.types import ToolCall

        msgs = [ChatMessage.assistant("", tool_calls=[ToolCall("calc", {"x": 1}, id="c1")])]
        out = _to_openai_messages(msgs)
        self.assertEqual(out[0]["tool_calls"][0]["function"]["name"], "calc")
        self.assertEqual(out[0]["tool_calls"][0]["id"], "c1")

    def test_anthropic_split_system(self):
        from distill.providers.anthropic_provider import _split_system

        system, convo = _split_system([ChatMessage.system("s"), ChatMessage.user("u")])
        self.assertEqual(system, "s")
        self.assertEqual(convo[0]["role"], "user")


if __name__ == "__main__":
    unittest.main()
