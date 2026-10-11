"""Tests for the data layer: filters, dedupe, formatters."""

import unittest

from distill.data import (
    FilterChain,
    Sample,
    exact_dedupe,
    format_alpaca,
    format_chat,
    format_sharegpt,
    format_text,
    near_dedupe,
    normalize_text,
)
from distill.types import ChatMessage


def make_sample(prompt="q", response="a"):
    return Sample(prompt=[ChatMessage.user(prompt)], response=ChatMessage.assistant(response))


class FilterTest(unittest.TestCase):
    def test_length_filter(self):
        chain = FilterChain.from_config([{"name": "length", "min_chars": 5, "max_chars": 10}])
        self.assertFalse(chain.apply(make_sample(response="hi")).keep)
        self.assertTrue(chain.apply(make_sample(response="hello")).keep)

    def test_banned_substrings(self):
        chain = FilterChain.from_config(
            [{"name": "banned_substrings", "substrings": ["as an ai language model"]}]
        )
        s = make_sample(response="As an AI language model, I cannot")
        self.assertFalse(chain.apply(s).keep)
        self.assertEqual(chain.stats.get("banned_substrings"), 1)

    def test_required_substrings_any(self):
        chain = FilterChain.from_config([{"name": "required_substrings", "substrings": ["yes", "no"]}])
        self.assertTrue(chain.apply(make_sample(response="yes")).keep)
        self.assertFalse(chain.apply(make_sample(response="maybe")).keep)

    def test_repetition_filter(self):
        chain = FilterChain.from_config([{"name": "repetition", "n": 3, "max_repeats": 1}])
        rep = " ".join(["a b c"] * 6)
        self.assertFalse(chain.apply(make_sample(response=rep)).keep)

    def test_regex_filter(self):
        chain = FilterChain.from_config([{"name": "regex", "pattern": r"^\d+$", "must_match": True}])
        self.assertTrue(chain.apply(make_sample(response="123")).keep)
        self.assertFalse(chain.apply(make_sample(response="abc")).keep)

    def test_filter_chain_filter_method(self):
        chain = FilterChain.from_config([{"name": "non_empty"}])
        kept = chain.filter([make_sample(response=""), make_sample(response="x")])
        self.assertEqual(len(kept), 1)


class DedupeTest(unittest.TestCase):
    def test_exact_dedupe(self):
        samples = [make_sample("q", "a"), make_sample("q", "a"), make_sample("q2", "b")]
        self.assertEqual(len(exact_dedupe(samples)), 2)

    def test_normalize(self):
        self.assertEqual(normalize_text("  Hello   World "), "hello world")

    def test_near_dedupe(self):
        base = "the quick brown fox jumps over the lazy dog again and again"
        samples = [
            make_sample("q1", base),
            make_sample("q2", base + "!"),  # near-identical
            make_sample("q3", "completely different content about distillation methods"),
        ]
        kept = near_dedupe(samples, threshold=0.6, k=4)
        self.assertLess(len(kept), 3)
        self.assertGreaterEqual(len(kept), 1)


class FormatterTest(unittest.TestCase):
    def test_chat(self):
        out = format_chat(make_sample("hi", "yo"))
        self.assertEqual(out["messages"][0]["role"], "user")
        self.assertEqual(out["messages"][1]["content"], "yo")

    def test_alpaca(self):
        out = format_alpaca(make_sample("instr", "resp"))
        self.assertEqual(out["instruction"], "instr")
        self.assertEqual(out["output"], "resp")

    def test_sharegpt(self):
        out = format_sharegpt(make_sample("hi", "yo"))
        self.assertEqual(out["conversations"][0]["from"], "human")
        self.assertEqual(out["conversations"][1]["from"], "gpt")

    def test_text(self):
        out = format_text(make_sample("hi", "yo"))
        self.assertIn("Assistant", out["text"])


if __name__ == "__main__":
    unittest.main()
