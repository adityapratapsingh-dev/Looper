"""Build providers from plain config dicts.

Example config fragment::

    teacher:
      provider: openai
      model: gpt-4o-mini
      api_key_env: OPENAI_API_KEY

    student:
      provider: hf
      model: Qwen/Qwen2.5-0.5B-Instruct
      device: cuda

``api_key_env`` names an environment variable to read the secret from; the
value is never written to disk.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from ..errors import ConfigError
from .base import Provider, get_provider


def _resolve_secrets(spec: Dict[str, Any]) -> Dict[str, Any]:
    env_name = spec.pop("api_key_env", None)
    if env_name and "api_key" not in spec:
        key = os.environ.get(env_name)
        if key:
            spec["api_key"] = key
    return spec


def build_provider(spec: Optional[Dict[str, Any]], default: Optional[str] = None) -> Provider:
    """Instantiate a provider from a config dict.

    ``spec`` keys: ``provider`` (registry name), ``model`` plus any provider
    kwargs. Unknown keys are passed through to the provider constructor.
    """

    spec = dict(spec or {})
    name = spec.pop("provider", None) or spec.pop("name", None) or default
    if not name:
        raise ConfigError("provider spec is missing a 'provider' name")
    model = spec.pop("model", None)
    spec = _resolve_secrets(spec)
    if model is None:
        # echo has a sensible default; others must specify a model.
        if name.lower() == "echo":
            model = "echo-1"
        else:
            raise ConfigError(f"provider '{name}' requires a 'model'")
    return get_provider(name, model, **spec)
