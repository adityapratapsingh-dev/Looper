"""Tests for losses, metrics and the eval harness."""

import unittest

from distill.eval import Evaluator, exact_match, normalized_edit_similarity, token_f1
from distill.eval.metrics import distinct_n, distribution_metrics
from distill.providers import get_provider
from distill.train.losses import (
    js_divergence,
    kl_divergence,
    softmax,
    temperature_scale,
)


class LossTest(unittest.TestCase):
    def test_softmax_sums_to_one(self):
        p = softmax([1.0, 2.0, 3.0])
        self.assertAlmostEqual(sum(p), 1.0, places=6)

    def test_softmax_temperature(self):
        sharp = softmax([1.0, 2.0, 3.0], temperature=0.1)
        flat = softmax([1.0, 2.0, 3.0], temperature=10.0)
        self.assertGreater(max(sharp), max(flat))

    def test_kl_zero_for_identical(self):
        p = [0.2, 0.3, 0.5]
        self.assertAlmostEqual(kl_divergence(p, p), 0.0, places=9)

    def test_kl_non_negative(self):
        self.assertGreaterEqual(kl_divergence([0.9, 0.1], [0.1, 0.9]), 0.0)

    def test_js_symmetric(self):
        p, q = [0.9, 0.1], [0.2, 0.8]
        self.assertAlmostEqual(js_divergence(p, q), js_divergence(q, p), places=9)

    def test_temperature_scale_identity(self):
        p = {"a": 0.5, "b": 0.5}
        self.assertEqual(temperature_scale(p, 1.0), p)

    def test_temperature_scale_normalises(self):
        out = temperature_scale({"a": 0.5, "b": 0.5}, 2.0)
        self.assertAlmostEqual(sum(out.values()), 1.0, places=9)


class MetricsTest(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(exact_match("Hello  World", "hello world"), 1.0)
        self.assertEqual(exact_match("a", "b"), 0.0)

    def test_token_f1(self):
        self.assertAlmostEqual(token_f1("the cat sat", "the cat sat"), 1.0)
        self.assertEqual(token_f1("a b", "c d"), 0.0)

    def test_edit_similarity(self):
        self.assertAlmostEqual(normalized_edit_similarity("a b c", "a b c"), 1.0)
        self.assertLess(normalized_edit_similarity("a b c", "a b c d e"), 1.0)

    def test_distinct_n(self):
        self.assertAlmostEqual(distinct_n(["a b a b", "a b a b"], 2), 1 / 3, places=6)

    def test_distribution_metrics(self):
        m = distribution_metrics([0.9, 0.1], [0.8, 0.2])
        self.assertIn("kl", m)
        self.assertEqual(m["top1_agreement"], 1.0)


class EvaluatorTest(unittest.TestCase):
    def test_evaluate_prompts(self):
        teacher = get_provider("echo")
        student = get_provider("echo")
        ev = Evaluator(teacher, student)
        result = ev.evaluate_prompts(["hello", "world"])
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.metrics["exact_match"], 1.0)  # identical providers

    def test_evaluate_agents(self):
        from distill.agent import default_registry, RunConfig

        teacher = get_provider("echo")
        student = get_provider("echo")
        ev = Evaluator(teacher, student)
        result = ev.evaluate_agents(
            ["search for distillation"],
            default_registry(),
            run_config=RunConfig(max_steps=3),
            verify_fn=lambda t: True,
            reward_fn=lambda t: 1.0,
        )
        self.assertEqual(result.metrics["teacher_success_rate"], 1.0)
        self.assertEqual(result.metrics["success_gap"], 0.0)


if __name__ == "__main__":
    unittest.main()
