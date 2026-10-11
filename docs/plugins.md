# Writing plugins

Everything in `distill` is looked up by name from a registry, so extending the
framework means registering a class or function under a name.

## Providers

```python
from distill.providers.base import Provider, ProviderCapabilities, register_provider
from distill.types import ChatMessage, Completion, SamplingParams, Usage

@register_provider("my_endpoint")
class MyEndpoint(Provider):
    name = "my_endpoint"

    def __init__(self, model, *, endpoint="", **kwargs):
        super().__init__(model, capabilities=ProviderCapabilities(tools=True), **kwargs)
        self.endpoint = endpoint

    def _chat_once(self, messages, *, tools, params, **kwargs) -> Completion:
        # call your HTTP/model backend here
        text = "..."
        return Completion(text=text, usage=Usage(completion_tokens=len(text.split())))
```

Then use it from a config:

```yaml
teacher:
  provider: my_endpoint
  model: my-model
  endpoint: https://...
```

For **logits-mode** teachers, also implement
`sequence_distributions(messages, target_ids) -> Tensor[T, V]` (see
`HuggingFaceProvider`).

## Filters

```python
from distill.registry import FILTERS
from distill.data.filters import FilterResult

@FILTERS.register("no_urls")
class NoUrlsFilter:
    name = "no_urls"
    def apply(self, sample):
        import re
        keep = not re.search(r"https?://", sample.completion)
        return FilterResult(keep=keep, filter=self.name)
```

## Formatters

```python
from distill.registry import FORMATTERS

@FORMATTERS.register("my_format")
def my_format(sample):
    return {"prompt": [m.to_dict() for m in sample.prompt],
            "completion": sample.completion}
```

## Tools (for agents)

```python
from distill.agent.tools import ToolRegistry, FunctionTool
from distill.types import ToolSpec

def ping(host: str) -> dict:
    """Ping a host."""
    return {"host": host, "ok": True}

registry = ToolRegistry().add(
    ping,
    name="ping",
    description="Ping a host.",
    parameters={"type": "object", "properties": {"host": {"type": "string"}},
                "required": ["host"]},
)
```

## Packaging plugins

Expose entry points so third parties can install your plugin and have the
registries find it automatically:

```toml
[project.entry-points."distill.plugins"]
"provider:my_endpoint" = "my_pkg.providers:MyEndpoint"
"filter:no_urls" = "my_pkg.filters:NoUrlsFilter"
```
