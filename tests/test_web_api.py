"""Tests for the Vercel serverless demo (api/demo.py)."""

import importlib.util
import unittest
from pathlib import Path

_DEMO_PATH = Path(__file__).resolve().parent.parent / "api" / "demo.py"


def load_demo():
    spec = importlib.util.spec_from_file_location("looper_demo", _DEMO_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DemoApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = load_demo()

    def test_catalogue(self):
        cat = self.demo._catalogue()
        self.assertEqual(cat["name"], "Looper")
        self.assertIn("data", cat["modes"])
        self.assertIn("echo", cat["providers"])
        self.assertIn("chat", cat["formatters"])

    def test_run_demo_returns_records(self):
        out = self.demo._run_demo({"prompts": "a task\nb task\na task", "format": "chat"})
        self.assertEqual(out["result"]["stats"]["generated"], 3)
        self.assertEqual(out["result"]["stats"]["after_dedupe"], 2)
        self.assertEqual(len(out["records"]), 2)
        self.assertIn("messages", out["records"][0])

    def test_run_demo_accepts_list_and_caps(self):
        out = self.demo._run_demo({"prompts": [f"task {i}" for i in range(50)]})
        self.assertLessEqual(out["result"]["stats"]["generated"], self.demo._MAX_PROMPTS)

    def test_run_demo_alpaca_format(self):
        out = self.demo._run_demo({"prompts": "hello", "format": "alpaca"})
        self.assertIn("instruction", out["records"][0])

    def test_run_demo_rejects_empty(self):
        with self.assertRaises(ValueError):
            self.demo._run_demo({"prompts": ""})

    def test_invalid_format_falls_back_to_chat(self):
        out = self.demo._run_demo({"prompts": "hi", "format": "nonsense"})
        self.assertEqual(out["result"]["stats"]["format"], "chat")


if __name__ == "__main__":
    unittest.main()
