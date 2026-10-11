"""Tests for the registry and provider factory."""

import unittest

from distill.errors import ConfigError, RegistryError
from distill.providers import get_provider
from distill.providers.echo import EchoProvider
from distill.providers.factory import build_provider
from distill.registry import PROVIDERS, Registry


class RegistryTest(unittest.TestCase):
    def test_register_and_get(self):
        reg = Registry("thing")

        @reg.register("a")
        def make(**kw):
            return kw

        self.assertIn("a", reg)
        self.assertEqual(reg.create("a", x=1), {"x": 1})
        self.assertEqual(reg.names(), ["a"])

    def test_duplicate_raises(self):
        reg = Registry("thing")

        @reg.register("a")
        def make():
            return 1

        with self.assertRaises(RegistryError):
            reg.add("a", lambda: 2)

    def test_unknown_raises(self):
        reg = Registry("thing")
        with self.assertRaises(RegistryError):
            reg.get("nope")

    def test_case_insensitive(self):
        reg = Registry("thing")
        reg.add("Mixed", lambda: 42)
        self.assertEqual(reg.get("mixed")(), 42)


class FactoryTest(unittest.TestCase):
    def test_build_echo_default(self):
        p = build_provider({"provider": "echo"})
        self.assertIsInstance(p, EchoProvider)

    def test_missing_provider_name(self):
        with self.assertRaises(ConfigError):
            build_provider({})

    def test_non_echo_requires_model(self):
        with self.assertRaises(ConfigError):
            build_provider({"provider": "openai"})

    def test_api_key_env_resolution(self):
        import os

        os.environ["_DISTILL_TEST_KEY"] = "secret123"
        p = build_provider({"provider": "openai", "model": "gpt-x", "api_key_env": "_DISTILL_TEST_KEY"})
        self.assertEqual(p.api_key, "secret123")

    def test_registered_providers_present(self):
        for name in ("echo", "openai", "anthropic", "hf"):
            self.assertIn(name, PROVIDERS)


if __name__ == "__main__":
    unittest.main()
