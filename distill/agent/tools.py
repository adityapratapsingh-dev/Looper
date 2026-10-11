"""Agent tools.

A tool is a named callable plus a JSON-schema :class:`ToolSpec`. The registry
maps tool names to implementations and executes :class:`ToolCall` objects,
turning results (or errors) into tool-result messages.
"""

from __future__ import annotations

import ast
import json
import operator
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..errors import ToolExecutionError
from ..types import ToolCall, ToolSpec

__all__ = [
    "Tool",
    "FunctionTool",
    "ToolRegistry",
    "calculator_tool",
    "word_count_tool",
    "knowledge_search_tool",
    "default_registry",
]


@dataclass
class FunctionTool:
    """A tool backed by a Python callable.

    The callable receives the tool-call ``arguments`` as keyword arguments and
    returns any JSON-serialisable value (or a string).
    """

    spec: ToolSpec
    fn: Callable[..., Any]
    name: str = ""

    def __post_init__(self) -> None:
        self.name = self.name or self.spec.name

    def run(self, arguments: Dict[str, Any]) -> Any:
        try:
            return self.fn(**arguments)
        except ToolExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface as a tool error
            raise ToolExecutionError(f"tool '{self.name}' failed: {exc}") from exc


Tool = FunctionTool


class ToolRegistry:
    """A collection of tools addressable by name."""

    def __init__(self, tools: Optional[List[FunctionTool]] = None) -> None:
        self._tools: Dict[str, FunctionTool] = {}
        for t in tools or []:
            self.register(t)

    def register(self, tool: FunctionTool) -> "ToolRegistry":
        self._tools[tool.name] = tool
        return self

    def add(
        self,
        fn: Callable[..., Any],
        name: Optional[str] = None,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> "ToolRegistry":
        spec = ToolSpec(
            name=name or fn.__name__,
            description=description or (fn.__doc__ or "").strip(),
            parameters=parameters or {"type": "object", "properties": {}},
        )
        return self.register(FunctionTool(spec=spec, fn=fn))

    def specs(self) -> List[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def names(self) -> List[str]:
        return sorted(self._tools)

    def get(self, name: str) -> Optional[FunctionTool]:
        return self._tools.get(name)

    def run(self, call: ToolCall) -> Any:
        tool = self._tools.get(call.name)
        if tool is None:
            raise ToolExecutionError(
                f"unknown tool '{call.name}'. Known: {', '.join(self.names())}"
            )
        return tool.run(call.arguments)

    def run_to_string(self, call: ToolCall) -> str:
        """Execute a call and always return a string (errors become text)."""

        try:
            result = self.run(call)
        except ToolExecutionError as exc:
            result = {"error": str(exc)}
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except TypeError:
            return str(result)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# -- built-in tools --------------------------------------------------------
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_ALLOWED_FUNCS = {"sqrt": __import__("math").sqrt, "abs": abs, "round": round}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = _ALLOWED_FUNCS.get(node.func.id)
        if fn is None:
            raise ValueError(f"function '{node.func.id}' is not allowed")
        return fn(*[_safe_eval(a) for a in node.args])
    raise ValueError("unsupported expression")


def calculator(expression: str) -> Dict[str, Any]:
    """Evaluate a basic arithmetic expression, e.g. '2 * (3 + 4)'."""

    tree = ast.parse(expression, mode="eval")
    return {"expression": expression, "result": _safe_eval(tree)}


def word_count(text: str) -> Dict[str, Any]:
    """Count words and characters in a piece of text."""

    words = text.split()
    return {"words": len(words), "characters": len(text)}


_KNOWLEDGE = {
    "distillation": (
        "Knowledge distillation trains a smaller student model to match a larger "
        "teacher's outputs (logits or generated text). Response distillation uses "
        "teacher-generated data; logit distillation matches soft probability targets."
    ),
    "agent": (
        "An AI agent interleaves reasoning with tool calls, observing results and "
        "iterating until it produces a final answer for the task."
    ),
    "lora": (
        "LoRA freezes base weights and trains low-rank adapter matrices, drastically "
        "reducing trainable parameters for fine-tuning and distillation."
    ),
}


def knowledge_search(query: str) -> Dict[str, Any]:
    """A tiny deterministic knowledge base for demos and tests."""

    q = query.lower()
    for key, value in _KNOWLEDGE.items():
        if key in q:
            return {"query": query, "snippet": value}
    return {"query": query, "snippet": "No matching entry found."}


def default_registry() -> ToolRegistry:
    """A registry containing the built-in demo tools."""

    reg = ToolRegistry()
    reg.add(
        calculator,
        name="calculator",
        description="Evaluate an arithmetic expression.",
        parameters={
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    )
    reg.add(
        word_count,
        name="word_count",
        description="Count words and characters in text.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )
    reg.add(
        knowledge_search,
        name="knowledge_search",
        description="Look up a short reference snippet about a topic.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    return reg

