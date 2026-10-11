# Architecture

`distill` is organized as four layers around one idea: **distillation is a
data-flow problem**, and every stage — teacher inference, filtering, training,
evaluation — should be swappable by name.

```
                       ┌───────────────────────────────────────────┐
                       │                Registry                   │
                       │  providers · modes · filters · formatters  │
                       │  evaluators                                │
                       └───────────────────────────────────────────┘
                                          ▲ name lookup
   ┌──────────┐   ┌──────────────┐   ┌────────────┐   ┌──────────────┐
   │ Provider │   │    Mode      │   │  Data/Train │   │    Eval      │
   │  layer   │──▶│ orchestrator │──▶│   layer     │──▶│  harness     │
   └──────────┘   └──────────────┘   └────────────┘   └──────────────┘
     teacher/        data              filters         metrics
     student         logits            dedupe          agreement
                     agent             formatters      success rate
```

## Layers

### 1. `distill.types` — the shared vocabulary
Plain dataclasses, JSON-serialisable, no dependencies:

- `ChatMessage` / `Role` / `ToolCall` / `ToolSpec` — conversations and tool use.
- `SamplingParams` — decoding knobs shared by every provider.
- `Completion` — a provider response (text, tool calls, `logprobs`, `usage`).
- `Trajectory` — a full agent episode.

Keeping these provider-agnostic is what lets the data and agent modes treat API
models, OpenAI-compatible servers and local transformers models identically.

### 2. `distill.providers` — teacher & student endpoints
A `Provider` turns messages into a `Completion`. `Provider.chat` adds retries,
timing and usage bookkeeping; subclasses implement only `_chat_once`.

| provider  | backend | tools | logprobs | white-box |
|-----------|---------|:-----:|:--------:|:---------:|
| `echo`    | none (deterministic, offline) | ✅ | ✅ | ✅ |
| `openai`  | OpenAI + any OpenAI-compatible server (vLLM, TGI, Ollama, Together…) | ✅ | ✅ | — |
| `anthropic` | Claude Messages API | ✅ | — | — |
| `hf`      | local `transformers` model | ✅ | ✅ | ✅ (full-vocab logits) |

White-box providers additionally implement `next_token_distribution` /
`sequence_distributions`, which the logits mode consumes to get *exact*
soft targets instead of top-k logprobs.

### 3. `distill.data` + `distill.agent` + `distill.train` — the mechanics
- **data**: `Sample`, composable `Filter`s, exact + MinHash `near_dedupe`,
  and formatters (`chat` / `alpaca` / `sharegpt` / `text`).
- **agent**: a `ToolRegistry`, an `AgentRunner` loop that records a
  `Trajectory`, and converters to behaviour-cloning or full-conversation data.
- **train**: `KnowledgeDistillationTrainer` (logits mode) and
  `SupervisedFineTuneTrainer` (data/agent modes), plus pure-Python losses.

### 4. `distill.modes` — the orchestrators
Each mode reads a config dict and returns a `ModeResult`:

| mode     | teacher used as | produces |
|----------|-----------------|----------|
| `data`   | response generator | filtered, deduped, formatted JSONL |
| `agent`  | tool-using agent | scored trajectories + BC/SFT examples |
| `logits` | white-box distribution | a distilled student checkpoint |

`RunConfig` executes a single mode or an ordered list of `stages`
(e.g. generate data → fine-tune → evaluate).

## Extensibility

Every stage is registered by name, so a plugin is a decorator:

```python
@register_provider("my_teacher")
class MyTeacher(Provider): ...

@FILTERS.register("my_filter")
class MyFilter: ...

@FORMATTERS.register("my_format")
def my_format(sample): ...
```

Third-party packages can also expose plugins via the `distill.plugins`
entry-point group (`"provider:<name>"`), which the registry loads on demand.

## Design decisions

- **Zero mandatory heavy dependencies.** The core (types, providers, data,
  agent, eval, CLI) runs on the standard library; `torch`/`transformers`/`openai`
  are imported lazily and raise `MissingDependencyError` with an install hint.
- **YAML with a built-in fallback.** PyYAML is used when present; a small
  subset parser keeps configs working in minimal environments.
- **Determinism for testing.** The `echo` provider is fully deterministic, so
  the whole framework is testable offline with no keys and no GPU.
- **Config-first, code-second.** Anything the CLI can do is expressible as a
  dict, and anything a dict can do is reachable from Python.
