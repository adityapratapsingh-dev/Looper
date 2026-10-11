"""Tests for config loading (YAML subset + JSON), env interpolation and CLI."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from distill import _yaml
from distill.config import RunConfig, interpolate_env, load_config


class MiniYamlTest(unittest.TestCase):
    def test_scalars_and_nesting(self):
        text = """
        mode: data
        teacher: {provider: echo, model: echo-1}
        prompts:
          - hello
          - world
        nested:
          a: 1
          b: true
          c: null
        """
        data = _yaml.loads(text)
        self.assertEqual(data["mode"], "data")
        self.assertEqual(data["teacher"]["provider"], "echo")
        self.assertEqual(data["prompts"], ["hello", "world"])
        self.assertEqual(data["nested"]["a"], 1)
        self.assertIs(data["nested"]["b"], True)
        self.assertIsNone(data["nested"]["c"])

    def test_list_of_maps(self):
        text = """
        filters:
          - name: length
            min_chars: 8
          - name: non_empty
        """
        data = _yaml.loads(text)
        self.assertEqual(len(data["filters"]), 2)
        self.assertEqual(data["filters"][0]["min_chars"], 8)

    def test_comments_and_quotes(self):
        text = """
        # a comment
        greeting: "hello: world"  # trailing
        """
        data = _yaml.loads(text)
        self.assertEqual(data["greeting"], "hello: world")


class ConfigTest(unittest.TestCase):
    def test_env_interpolation(self):
        os.environ["_DISTILL_ENV"] = "xyz"
        self.assertEqual(interpolate_env("a-${_DISTILL_ENV}"), "a-xyz")
        self.assertEqual(interpolate_env({"k": ["${_DISTILL_ENV}"]}), {"k": ["xyz"]})

    def test_load_json_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "c.json"
            p.write_text(json.dumps({"mode": "data", "prompts": ["hi"]}))
            cfg = load_config(p)
            self.assertEqual(cfg["mode"], "data")

    def test_run_config_requires_mode(self):
        with self.assertRaises(Exception):
            RunConfig.from_dict({"prompts": ["x"]})

    def test_run_config_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "o.jsonl"
            cfg = RunConfig.from_dict(
                {
                    "stages": [
                        {
                            "mode": "data",
                            "teacher": {"provider": "echo"},
                            "prompts": ["hi", "there"],
                            "output": str(out),
                        }
                    ]
                }
            )
            results = cfg.run()
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].mode, "data")
            self.assertTrue(out.exists())


class CliTest(unittest.TestCase):
    def test_list_command(self):
        from distill.cli import main

        self.assertEqual(main(["list"]), 0)

    def test_version_command(self):
        from distill.cli import main

        self.assertEqual(main(["version"]), 0)

    def test_run_command(self):
        from distill.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "o.jsonl"
            cfg = Path(tmp) / "c.yaml"
            cfg.write_text(
                "mode: data\nteacher: {provider: echo}\nprompts: [hello]\noutput: %s\n" % out
            )
            self.assertEqual(main(["run", str(cfg)]), 0)
            self.assertTrue(out.exists())

    def test_run_missing_config_returns_error(self):
        from distill.cli import main

        self.assertNotEqual(main(["run", "/nonexistent/config.yaml"]), 0)


if __name__ == "__main__":
    unittest.main()


class ConfigErrorTest(unittest.TestCase):
    def test_malformed_json_raises_config_error(self):
        from distill.errors import ConfigError

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text("{ not json")
            with self.assertRaises(ConfigError):
                load_config(p)

    def test_missing_config_raises_config_error(self):
        from distill.errors import ConfigError

        with self.assertRaises(ConfigError):
            load_config("/definitely/not/here.yaml")
