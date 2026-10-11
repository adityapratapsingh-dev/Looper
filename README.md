# Looper — distillation for LLMs and AI agents

A pluggable framework for distilling large models and capable agents into
smaller, cheaper students. One backbone, three first-class modes:

| mode | what it does | needs |
|------|--------------|-------|
| **`data`** | A teacher generates synthetic responses; they are filtered, de-duplicated and formatted into fine-tuning data. | any chat model |
| **`agent`** | A teacher *agent* (with tools) solves tasks; full trajectories are captured, scored and turned into behaviour-cloning / SFT data. | any chat model + tools |
| **`logits`** | Classic knowledge distillation: a small student is trained to match a white-box teacher's temperature-scaled token distribution. | local model + torch |

Providers, filters, formatters, tools and modes are all **registered by name**,
so swapping a teacher, a scoring rule or an export format is a one-line config
change — or a one-decorator plugin.

```
 teacher (API / local) ──▶ mode orchestrator ──▶ filters · dedupe · format ──▶ dataset
                                                   │
                                                   └─▶ train (SFT / KD) ──▶ student
                                                                 │
                                                       eval harness (agreement, success rate)
```

## Install

```bash
pip install -e .                 # core: stdlib only + optional PyYAML
pip install -e '.[openai]'       # OpenAI / OpenAI-compatible teachers
pip install -e '.[anthropic]'    # Claude teachers
pip install -e '.[hf]'           # local transformers providers
pip install -e '.[train]'        # torch trainers (logits KD + SFT)
pip install -e '.[all]'
```

The core runs with **no heavy dependencies** — `torch`, `transformers`,
`openai` and `anthropic` are imported lazily and only when needed.

## Quickstart (offline, no keys)

```bash
python -m distill list                       # registered modes/providers/filters/formatters
distill run configs/data_synthesis.yaml      # generate training data
distill run configs/agent_distill.yaml       # capture agent trajectories
distill eval my_eval.yaml                     # compare teacher vs student
```

Or from Python:

```python
from distill.modes import get_mode

result = get_mode("data")({
    "teacher": {"provider": "echo"},          # swap for openai / anthropic / hf
    "prompts": ["Explain knowledge distillation.", "What is LoRA?"],
    "filters": [{"name": "non_empty"}, {"name": "length", "min_chars": 20}],
    "dedupe": {"exact": True, "near": {"enabled": True, "threshold": 0.85}},
    "format": "chat",
    "output": "data/processed/teacher.jsonl",
}).run()
print(result.num_examples, result.stats)
```

See `examples/` for data, agent, evaluation and plugin walkthroughs.

## Using a real teacher

```yaml
mode: data
teacher:
  provider: openai            # or anthropic, hf, or any OpenAI-compatible server
  model: gpt-4o-mini
  api_key_env: OPENAI_API_KEY # secrets stay in the environment
prompts_file: prompts.txt
output: data/processed/distill.jsonl
```

Point `base_url` at a vLLM / TGI / Ollama / Together endpoint and the same
config distils a self-hosted model:

```yaml
teacher:
  provider: openai
  model: Qwen/Qwen2.5-72B-Instruct
  base_url: http://localhost:8000/v1
```

## Agent distillation

```yaml
mode: agent
teacher: {provider: openai, model: gpt-4o, api_key_env: OPENAI_API_KEY}
tasks: ["Search for X", "Calculate 128*4", "Summarise Y"]
tools: default                 # calculator, word_count, knowledge_search (or your own)
max_steps: 6
verifier: {type: contains, value: "answer"}
filter: {succeeded_only: true}
format: bc                     # behaviour cloning: one example per assistant turn
output: trajectories.jsonl
export: agent_train.jsonl
```

Each episode is captured as a `Trajectory` (reasoning, tool calls, tool results),
scored, filtered, and exported as per-step behaviour-cloning targets or whole
dialogues for SFT. Add your own tools with `ToolRegistry.add(fn, name=..., parameters=...)`.

## Logits (classic) distillation

```yaml
mode: logits
teacher: {provider: hf, model: Qwen/Qwen2.5-1.5B-Instruct}
student: {model: Qwen/Qwen2.5-0.5B-Instruct}
data: data/processed/teacher_data.samples.jsonl
kd: {temperature: 2.0, alpha: 0.9, lr: 5.0e-5, epochs: 3, use_lora: true}
```

The loss is the Hinton formulation, `alpha·T²·KL(student/T ‖ teacher/T) +
(1-alpha)·CE(student, y)`, with automatic vocabulary alignment when teacher and
student tokenizers differ.

## Chaining stages

```yaml
stages:
  - mode: data
    teacher: {provider: echo}
    prompts: ["...", "..."]
    output: data/processed/d.jsonl
  - mode: logits
    teacher: {provider: hf, model: <teacher-id>}
    student: {model: <student-id>}
    data: data/processed/d.samples.jsonl
```

## Architecture & docs

- `docs/DEPLOY.md` — hosting the demo on Vercel (static site + Python serverless API).
- `docs/architecture.md` — layer-by-layer design and rationale.
- `docs/plugins.md` — custom providers, filters, formatters, tools, entry points.

## Tests

```bash
python -m unittest discover -s tests      # offline, deterministic, no keys/GPU
```

## Project layout

```
distill/            # the package
  types.py          # ChatMessage, Completion, Trajectory, ...
  registry.py       # named-plugin registries
  config.py         # YAML/JSON run configs (built-in YAML fallback)
  providers/        # echo · openai-compat · anthropic · hf   (+ factory)
  data/             # Sample · filters · dedupe · formatters
  agent/            # tools · AgentRunner · trajectory handling
  modes/            # data · agent · logits orchestrators
  train/            # KD & SFT trainers, losses, model loading
  eval/             # metrics + teacher/student harness
  cli.py            # `distill` command
tests/              # stdlib unittest suite
configs/            # ready-to-run example configs
examples/           # runnable quickstarts and plugin demos
docs/               # architecture and plugin guides
```

## License

MIT.
