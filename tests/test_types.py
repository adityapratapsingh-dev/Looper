"""Tests for core types and serialisation round-trips."""

import unittest

from distill.types import (
    ChatMessage,
    Completion,
    Role,
    SamplingParams,
    TokenLogprob,
    ToolCall,
    ToolSpec,
    Trajectory,
    Usage,
)


class TypesTest(unittest.TestCase):
    def test_chat_message_roundtrip(self):
        msg = ChatMessage.assistant(
            "hello", tool_calls=[ToolCall("search", {"q": "x"}, id="c1")]
        )
        d = msg.to_dict()
        self.assertEqual(d["role"], "assistant")
        self.assertEqual(d["tool_calls"][0]["name"], "search")
        again = ChatMessage.from_dict(d)
        self.assertEqual(again.role, Role.ASSISTANT)
        self.assertEqual(again.tool_calls[0].arguments, {"q": "x"})
        self.assertEqual(again.tool_calls[0].id, "c1")

    def test_toolcall_from_json_string_arguments(self):
        call = ToolCall.from_dict({"name": "calc", "arguments": '{"x": 1}', "id": "z"})
        self.assertEqual(call.arguments, {"x": 1})

    def test_toolcall_from_bad_json(self):
        call = ToolCall.from_dict({"name": "calc", "arguments": "not json"})
        self.assertEqual(call.arguments, {"_raw": "not json"})

    def test_sampling_params_extra(self):
        p = SamplingParams.from_dict({"temperature": 0.3, "custom": 7})
        self.assertEqual(p.temperature, 0.3)
        self.assertEqual(p.extra["custom"], 7)

    def test_completion_roundtrip(self):
        c = Completion(
            text="hi",
            logprobs=[TokenLogprob("hi", -0.5, [("hi", -0.5)])],
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
        d = c.to_dict()
        back = Completion.from_dict(d)
        self.assertEqual(back.text, "hi")
        self.assertEqual(back.logprobs[0].token, "hi")
        self.assertEqual(back.usage.total_tokens, 2)

    def test_trajectory_counts_steps(self):
        t = Trajectory(task="do it")
        t.add(ChatMessage.user("do it"))
        t.add(ChatMessage.assistant("", tool_calls=[ToolCall("t", {})]))
        t.add(ChatMessage.tool("result", "call_1"))
        t.add(ChatMessage.assistant("done"))
        self.assertEqual(t.num_steps, 2)
        back = Trajectory.from_dict(t.to_dict())
        self.assertEqual(back.num_steps, 2)
        self.assertEqual(len(back.messages), 4)

    def test_toolspec_openai_shape(self):
        spec = ToolSpec("f", "desc", {"type": "object", "properties": {}})
        oa = spec.to_openai()
        self.assertEqual(oa["type"], "function")
        self.assertEqual(oa["function"]["name"], "f")


if __name__ == "__main__":
    unittest.main()
