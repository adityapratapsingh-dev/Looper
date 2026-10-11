"""Data (black-box response) distillation.

A teacher model generates responses to a set of prompts; the responses are
filtered, de-duplicated and formatted into training data for a student.

Config keys
-----------
teacher        : provider spec (see providers.factory)
prompts        : list[str]  OR  prompts_file: path (one prompt per line)
system_prompt  : optional system message prepended to every prompt
sampling       : SamplingParams dict
filters        : list of filter specs (see data.filters)
dedupe         : {"exact": bool, "near": {"enabled": bool, "threshold": float}}
limit          : keep at most N samples (after dedupe)
format         : chat | alpaca | sharegpt | text   (default: chat)
output         : path to write the formatted JSONL
max_workers    : parallel teacher calls (default 1)
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..agent.trajectory import write_jsonl
from ..data import (
    FilterChain,
    Sample,
    exact_dedupe,
    get_formatter,
    near_dedupe,
)
from ..providers.factory import build_provider
from ..types import ChatMessage, SamplingParams
from .base import Mode, ModeResult, register_mode

__all__ = ["DataDistillationMode"]


@register_mode("data")
class DataDistillationMode(Mode):
    name = "data"

    def run(self) -> ModeResult:
        cfg = self.config
        teacher = build_provider(cfg.get("teacher"), default="echo")
        params = SamplingParams.from_dict(cfg.get("sampling", {}) or {})
        prompts = self._load_prompts(cfg)
        system_prompt = cfg.get("system_prompt")
        max_workers = int(cfg.get("max_workers", 1) or 1)

        def generate(prompt: str) -> Sample:
            messages: List[ChatMessage] = []
            if system_prompt:
                messages.append(ChatMessage.system(system_prompt))
            messages.append(ChatMessage.user(prompt))
            completion = teacher.chat(messages, params=params)
            return Sample(
                prompt=messages,
                response=completion.message or ChatMessage.assistant(completion.text),
                source=f"{teacher.name}:{teacher.model}",
                teacher_logprobs=completion.logprobs,
                metadata={"usage": completion.usage.to_dict()},
            )

        if max_workers > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                raw = list(pool.map(generate, prompts))
        else:
            raw = [generate(p) for p in prompts]

        stats: Dict[str, Any] = {"generated": len(raw)}
        filters = FilterChain.from_config(cfg.get("filters", []) or [])
        kept = filters.filter(raw)
        stats["after_filters"] = len(kept)
        stats["filter_rejections"] = dict(filters.stats)

        dedupe_cfg = cfg.get("dedupe", {}) or {}
        if dedupe_cfg.get("exact", True):
            kept = exact_dedupe(kept)
        d_near = dedupe_cfg.get("near") or {}
        if isinstance(d_near, dict) and d_near.get("enabled"):
            kept = near_dedupe(
                kept,
                threshold=float(d_near.get("threshold", 0.85)),
                num_perm=int(d_near.get("num_perm", 64)),
                k=int(d_near.get("k", 5)),
            )
        stats["after_dedupe"] = len(kept)

        limit = cfg.get("limit")
        if limit:
            kept = kept[: int(limit)]

        fmt_name = cfg.get("format", "chat")
        formatter = get_formatter(fmt_name)
        records = [formatter(s) for s in kept]

        output = cfg.get("output")
        if output:
            write_jsonl(output, records)
            # Also persist the rich sample records (logprobs, metadata, usage).
            write_jsonl(str(Path(output).with_suffix(".samples.jsonl")), (s.to_dict() for s in kept))

        stats["teacher"] = f"{teacher.name}:{teacher.model}"
        stats["format"] = fmt_name
        return ModeResult(
            mode=self.name,
            output_path=output,
            num_examples=len(records),
            stats=stats,
        )

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _load_prompts(cfg: Dict[str, Any]) -> List[str]:
        prompts: List[str] = list(cfg.get("prompts", []) or [])
        prompts_file: Optional[str] = cfg.get("prompts_file")
        if prompts_file:
            text = Path(prompts_file).read_text(encoding="utf-8")
            prompts.extend(
                line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")
            )
        if not prompts:
            raise ValueError("data mode requires 'prompts' or 'prompts_file'")
        return prompts
