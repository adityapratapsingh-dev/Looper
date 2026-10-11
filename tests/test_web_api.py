"""Tests for the Vercel serverless entrypoint (api/index.py)."""

import importlib.util
import unittest
from pathlib import Path

_ENTRY = Path(__file__).resolve().parent.parent / "api" / "index.py"


def load_entry():
    spec = importlib.util.spec_from_file_location("looper_entry", _ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DistillEndpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = load_entry()

    def test_runs_real_data_mode(self):
        status, body = self.entry._distill({"prompts": "a task\nb task\na task", "format": "chat"})
        self.assertEqual(status, 200)
        self.assertEqual(body["result"]["stats"]["generated"], 3)
        self.assertEqual(body["result"]["stats"]["after_dedupe"], 2)
        self.assertIn("messages", body["records"][0])

    def test_alpaca_format(self):
        status, body = self.entry._distill({"prompts": "hello", "format": "alpaca"})
        self.assertIn("instruction", body["records"][0])

    def test_rejects_empty(self):
        status, body = self.entry._distill({"prompts": ""})
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_invalid_format_falls_back(self):
        status, body = self.entry._distill({"prompts": "hi", "format": "nonsense"})
        self.assertEqual(body["result"]["stats"]["format"], "chat")

    def test_caps_prompt_count(self):
        status, body = self.entry._distill({"prompts": [f"task {i}" for i in range(50)]})
        self.assertLessEqual(body["result"]["stats"]["generated"], 25)


class HandlerTest(unittest.TestCase):
    def test_handler_is_a_class(self):
        entry = load_entry()
        self.assertTrue(hasattr(entry, "handler"))
        for verb in ("do_GET", "do_POST", "do_DELETE", "do_OPTIONS"):
            self.assertTrue(hasattr(entry.handler, verb), verb)


if __name__ == "__main__":
    unittest.main()
