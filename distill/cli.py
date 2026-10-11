"""Command-line interface: ``distill <command>``.

Commands
--------
run <config.yaml>     Execute a distillation config (data | logits | agent | stages).
eval <config.yaml>    Compare a teacher and student (text or agent tasks).
list                  Show registered modes, providers, filters, formatters.
version               Print the framework version.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from .config import RunConfig, load_config
from .errors import DistillError
from .registry import FILTERS, FORMATTERS, MODES, PROVIDERS


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_run(args: argparse.Namespace) -> int:
    config = RunConfig.from_file(args.config)
    results = config.run()
    summary = {"stages": [r.to_dict() for r in results]}
    _print(summary)
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from .eval import Evaluator
    from .providers.factory import build_provider
    from .types import SamplingParams

    cfg = load_config(args.config)
    teacher = build_provider(cfg.get("teacher"), default="echo")
    student = build_provider(cfg.get("student"), default="echo")
    params = SamplingParams.from_dict(cfg.get("sampling", {}) or {})
    evaluator = Evaluator(teacher, student, params=params)

    agent_cfg = cfg.get("agent")
    if agent_cfg:
        from .agent.tools import default_registry
        from .agent.runner import RunConfig as RunCfg
        from .modes.agent import _make_verifier

        tasks = list(agent_cfg.get("tasks", []) or [])
        run_cfg = RunCfg(
            max_steps=int(agent_cfg.get("max_steps", 6)),
            system_prompt=agent_cfg.get("system_prompt"),
            params=params,
        )
        verifier = _make_verifier(agent_cfg.get("verifier"))
        reward_fn = (lambda t: 1.0 if t.success else 0.0) if verifier else None
        result = evaluator.evaluate_agents(
            tasks, default_registry(), run_config=run_cfg, reward_fn=reward_fn, verify_fn=verifier
        )
    else:
        prompts = list(cfg.get("prompts", []) or [])
        if not prompts:
            print("error: eval config needs 'prompts' or 'agent.tasks'", file=sys.stderr)
            return 2
        result = evaluator.evaluate_prompts(prompts, system_prompt=cfg.get("system_prompt"))

    out: Dict[str, Any] = result.to_dict()
    if args.show_rows:
        out["rows"] = result.rows
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    _print(out)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    import distill.modes  # noqa: F401  (ensures modes self-register)
    import distill.data  # noqa: F401  (ensures filters/formatters self-register)
    import distill.providers  # noqa: F401

    _print(
        {
            "modes": MODES.names(),
            "providers": PROVIDERS.names(),
            "filters": FILTERS.names(),
            "formatters": FORMATTERS.names(),
        }
    )
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    print(f"distill {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="distill", description="LLM & agent distillation framework")
    parser.add_argument("--version", action="version", version=f"distill {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run a distillation config")
    p_run.add_argument("config", help="path to a YAML/JSON config")
    p_run.set_defaults(func=cmd_run)

    p_eval = sub.add_parser("eval", help="evaluate a student against a teacher")
    p_eval.add_argument("config", help="path to an eval config")
    p_eval.add_argument("--show-rows", action="store_true", help="include per-example rows")
    p_eval.add_argument("--output", help="write results JSON to this path")
    p_eval.set_defaults(func=cmd_eval)

    p_list = sub.add_parser("list", help="list registered components")
    p_list.set_defaults(func=cmd_list)

    p_ver = sub.add_parser("version", help="print version")
    p_ver.set_defaults(func=cmd_version)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except DistillError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
