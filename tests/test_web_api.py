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


class HandlerTest(unittest.TestCase):
    def test_handler_is_a_class(self):
        entry = load_entry()
        self.assertTrue(hasattr(entry, "handler"))
        for verb in ("do_GET", "do_POST", "do_DELETE", "do_OPTIONS"):
            self.assertTrue(hasattr(entry.handler, verb), verb)

    def test_entry_exposes_platform_handle(self):
        entry = load_entry()
        status, body = entry.platform_handle("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_entry_has_no_distill_route(self):
        entry = load_entry()
        self.assertFalse(hasattr(entry, "run_data_mode"))
        status, _ = entry.platform_handle("POST", "/api/distill", body={"prompts": "x"})
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
