"""Extending the framework: custom provider, tool, filter and formatter.

Everything in `distill` is registered by name, so a plugin is just a decorator.

    python examples/custom_plugin.py
"""

from __future__ import annotations

from typing import List, Sequence

from distill.agent.tools import ToolRegistry
from distill.data import FilterChain, Sample, get_formatter
from distill.providers.base import Provider, ProviderCapabilities, register_provider
from distill.registry import FILTERS, FORMATTERS
from distill.types import ChatMessage, Completion, SamplingParams, ToolSpec, Usage


# 1) A custom provider ------------------------------------------------------
@register_provider("upper")
class UpperProvider(Provider):
    """A silly provider that upper-cases the last user message."""

    name = "upper"

    def __init__(self, model: str = "upper-1", **kwargs):
        super().__init__(model, capabilities=ProviderCapabilities(), **kwargs)

    def _chat_once(self, messages, *, tools, params: SamplingParams, **kwargs) -> Completion:
        text = messages[-1].content.upper()
        return Completion(
            text=text,
            usage=Usage(completion_tokens=len(text.split())),
            model=self.model,
        )


# 2) A custom filter --------------------------------------------------------
@FILTERS.register("starts_with")
class StartsWithFilter:
    name = "starts_with"

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix

    def apply(self, sample: Sample):
        from distill.data.filters import FilterResult

        keep = sample.completion.startswith(self.prefix)
        return FilterResult(keep=keep, filter=self.name)


# 3) A custom formatter -----------------------------------------------------
@FORMATTERS.register("lines")
def format_lines(sample: Sample):
    return {"prompt": "\n".join(m.text() for m in sample.prompt), "completion": sample.completion}


# 4) A custom tool ----------------------------------------------------------
def shout(text: str) -> dict:
    """Return the text upper-cased."""
    return {"shouted": text.upper()}


def main() -> None:
    # Provider
    from distill.providers import get_provider

    provider = get_provider("upper")
    print("custom provider ->", provider.chat([ChatMessage.user("hello plugins")]).text)

    # Filter
    chain = FilterChain.from_config([{"name": "starts_with", "prefix": "HELLO"}])
    sample = Sample(prompt=[ChatMessage.user("x")], response=ChatMessage.assistant("HELLO there"))
    print("custom filter keep ->", chain.apply(sample).keep)

    # Formatter
    print("custom formatter ->", get_formatter("lines")(sample))

    # Tool
    reg = ToolRegistry().add(
        shout,
        name="shout",
        description="Upper-case text.",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}},
    )
    from distill.types import ToolCall

    print("custom tool ->", reg.run_to_string(ToolCall("shout", {"text": "hi"})))


if __name__ == "__main__":
    main()
