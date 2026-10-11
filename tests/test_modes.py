"""End-to-end tests for the data and agent modes (offline, via the echo provider)."""

import json
import tempfile
import unittest
from pathlib import Path

from distill.modes import get_mode


class DataModeTest(unittest.TestCase):
    def test_data_mode_writes_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "data.jsonl"
            cfg = {
                "mode": "data",
                "teacher": {"provider": "echo"},
                "prompts": ["What is distillation?", "Explain LoRA.", "What is distillation?"],
                "sampling": {"temperature": 0.8, "max_tokens": 64},
                "filters": [{"name": "length", "min_chars": 5}],
                "dedupe": {"exact": True, "near": {"enabled": True, "threshold": 0.9}},
                "format": "chat",
                "output": str(out),
            }
            result = get_mode("data")(cfg).run()
            self.assertEqual(result.mode, "data")
            self.assertEqual(result.stats["generated"], 3)
            self.assertEqual(result.num_examples, 2)  # duplicate collapsed
            self.assertTrue(out.exists())
            first = json.loads(out.read_text().splitlines()[0])
            self.assertIn("messages", first)
            self.assertTrue(Path(tmp, "data.samples.jsonl").exists())

    def test_data_mode_requires_prompts(self):
        with self.assertRaises(ValueError):
            get_mode("data")({"mode": "data", "teacher": {"provider": "echo"}}).run()

    def test_data_mode_alpaca_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "d.jsonl"
            cfg = {
                "teacher": {"provider": "echo"},
                "prompts": ["hello"],
                "format": "alpaca",
                "output": str(out),
            }
            get_mode("data")(cfg).run()
            rec = json.loads(out.read_text().splitlines()[0])
            self.assertIn("instruction", rec)
            self.assertIn("output", rec)


class AgentModeTest(unittest.TestCase):
    def test_agent_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "trajs.jsonl"
            export = Path(tmp) / "train.jsonl"
            cfg = {
                "mode": "agent",
                "teacher": {"provider": "echo"},
                "tasks": ["please search for distillation", "explain distillation"],
                "tools": "default",
                "system_prompt": "You are a helpful agent.",
                "max_steps": 4,
                "verifier": {"type": "contains", "value": "distillation"},
                "format": "bc",
                "output": str(out),
                "export": str(export),
            }
            result = get_mode("agent")(cfg).run()
            self.assertEqual(result.stats["num_tasks"], 2)
            self.assertEqual(result.stats["success_rate"], 1.0)
            self.assertTrue(out.exists())
            self.assertTrue(export.exists())
            self.assertGreater(result.num_examples, 0)

    def test_agent_mode_tool_subset(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {
                "teacher": {"provider": "echo"},
                "tasks": ["calculate 1 + 1"],
                "tools": ["calculator"],
                "max_steps": 3,
                "output": str(Path(tmp) / "t.jsonl"),
            }
            result = get_mode("agent")(cfg).run()
            self.assertEqual(result.stats["tools"], ["calculator"])

    def test_agent_mode_requires_tasks(self):
        with self.assertRaises(ValueError):
            get_mode("agent")({"mode": "agent", "teacher": {"provider": "echo"}}).run()


if __name__ == "__main__":
    unittest.main()
