"""Providers: the pluggable teacher/student interface.

A provider is anything that can turn a list of :class:`ChatMessage` into a
:class:`Completion`. This unifies:

* black-box API models (OpenAI, Anthropic, ...),
* self-hosted / OpenAI-compatible servers (vLLM, TGI, Ollama, Together, ...),
* local transformers models with white-box access to logits.

Configs and code refer to providers by registry name, e.g.
``distill.providers.get("openai")``.
"""

from .base import Provider, ProviderCapabilities, get_provider, register_provider

# Import built-in providers so that they self-register. Optional providers fail
# soft: their dependencies are only required when the provider is constructed.
from . import echo as _echo  # noqa: F401,E402
from . import openai_compat as _openai  # noqa: F401,E402
from . import anthropic_provider as _anthropic  # noqa: F401,E402
from . import hf_local as _hf  # noqa: F401,E402

__all__ = [
    "Provider",
    "ProviderCapabilities",
    "get_provider",
    "register_provider",
]
