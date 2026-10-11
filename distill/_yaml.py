"""A tiny YAML-subset parser used when PyYAML is unavailable.

Supports the subset the framework's configs actually use:

* block mappings and sequences (indentation based),
* sequences of mappings,
* inline flow collections ``{a: 1, b: [x, y]}``,
* single/double quoted and bare scalars, ints, floats, booleans, ``null``/``~``,
* ``#`` comments.

It is intentionally small and dependency-free; install PyYAML for the full spec.
"""

from __future__ import annotations

from typing import Any, List, Tuple

__all__ = ["loads", "load"]


def _strip_comment(line: str) -> str:
    out: List[str] = []
    quote: str | None = None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            continue
        if ch == "#":
            break
        out.append(ch)
    return "".join(out).rstrip()


def _preprocess(text: str) -> List[Tuple[int, str]]:
    rows: List[Tuple[int, str]] = []
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        rows.append((indent, line.strip()))
    return rows


def _split_key(content: str) -> Tuple[str, str]:
    quote: str | None = None
    depth = 0
    for i, ch in enumerate(content):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == ":" and depth == 0:
            return content[:i].strip(), content[i + 1 :].strip()
    return content.strip(), ""


def _split_flow(content: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    quote: str | None = None
    current: List[str] = []
    for ch in content:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            current.append(ch)
        elif ch in "[{":
            depth += 1
            current.append(ch)
        elif ch in "]}":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]


def _scalar(token: str) -> Any:
    token = token.strip()
    if token == "":
        return None
    if token[0] == "{" and token[-1] == "}":
        result = {}
        for part in _split_flow(token[1:-1]):
            k, v = _split_key(part)
            result[k.strip("'\"")] = _scalar(v)
        return result
    if token[0] == "[" and token[-1] == "]":
        return [_scalar(p) for p in _split_flow(token[1:-1])]
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    lowered = token.lower()
    if lowered in ("null", "~"):
        return None
    if lowered in ("true", "yes"):
        return True
    if lowered in ("false", "no"):
        return False
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass
    return token


def _parse_block(rows: List[Tuple[int, str]], i: int, indent: int) -> Tuple[Any, int]:
    if i >= len(rows):
        return None, i
    if rows[i][1].startswith("- "):
        return _parse_list(rows, i, indent)
    return _parse_map(rows, i, indent)


def _parse_map(rows: List[Tuple[int, str]], i: int, indent: int) -> Tuple[dict, int]:
    result: dict = {}
    while i < len(rows) and rows[i][0] >= indent:
        cur_indent, content = rows[i]
        if content.startswith("- "):
            break
        key, rest = _split_key(content)
        if rest == "":
            if i + 1 < len(rows) and rows[i + 1][0] > cur_indent:
                value, i = _parse_block(rows, i + 1, rows[i + 1][0])
            else:
                value, i = None, i + 1
        else:
            value, i = _scalar(rest), i + 1
        result[key.strip("'\"")] = value
    return result, i


def _parse_list(rows: List[Tuple[int, str]], i: int, indent: int) -> Tuple[list, int]:
    items: list = []
    while i < len(rows) and rows[i][0] >= indent and rows[i][1].startswith("- "):
        cur_indent, content = rows[i]
        rest = content[2:].strip()
        item_indent = cur_indent + 2
        if rest == "":
            if i + 1 < len(rows) and rows[i + 1][0] > cur_indent:
                value, i = _parse_block(rows, i + 1, rows[i + 1][0])
            else:
                value, i = None, i + 1
            items.append(value)
            continue
        if ":" in rest and not rest.startswith(("{", "[")):
            entry: dict = {}
            key, val = _split_key(rest)
            if val == "":
                if i + 1 < len(rows) and rows[i + 1][0] > item_indent:
                    val, i = _parse_block(rows, i + 1, rows[i + 1][0])
                else:
                    val, i = None, i + 1
            else:
                val, i = _scalar(val), i + 1
            entry[key.strip("'\"")] = val
            while i < len(rows) and rows[i][0] >= item_indent:
                k2, v2 = _split_key(rows[i][1])
                if v2 == "":
                    if i + 1 < len(rows) and rows[i + 1][0] > rows[i][0]:
                        v2, i = _parse_block(rows, i + 1, rows[i + 1][0])
                    else:
                        v2, i = None, i + 1
                else:
                    v2, i = _scalar(v2), i + 1
                entry[k2.strip("'\"")] = v2
            items.append(entry)
        else:
            items.append(_scalar(rest))
            i += 1
    return items, i


def loads(text: str) -> Any:
    """Parse a YAML-subset document into Python objects."""

    rows = _preprocess(text)
    if not rows:
        return {}
    value, _ = _parse_block(rows, 0, rows[0][0])
    return value


def load(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return loads(f.read())

