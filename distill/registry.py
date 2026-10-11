"""A tiny, dependency-free registry used to make providers, modes, filters and
evaluators pluggable by name (including through config files and entry points).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Generic, Iterable, List, TypeVar

from .errors import RegistryError

T = TypeVar("T")

_ENTRY_POINT_GROUP = "distill.plugins"


class Registry(Generic[T]):
    """A name -> factory mapping with decorator-based registration."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._items: Dict[str, Callable[..., T]] = {}
        self._loaded = False

    # -- registration ------------------------------------------------------
    def register(self, name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
        def deco(fn: Callable[..., T]) -> Callable[..., T]:
            key = name.lower()
            if key in self._items:
                raise RegistryError(f"{self.kind} '{name}' is already registered")
            self._items[key] = fn
            return fn

        return deco

    def add(self, name: str, factory: Callable[..., T]) -> None:
        key = name.lower()
        if key in self._items:
            raise RegistryError(f"{self.kind} '{name}' is already registered")
        self._items[key] = factory

    # -- access ------------------------------------------------------------
    def get(self, name: str) -> Callable[..., T]:
        self._maybe_load_entry_points()
        key = name.lower()
        if key not in self._items:
            available = ", ".join(sorted(self._items)) or "<none>"
            raise RegistryError(
                f"Unknown {self.kind} '{name}'. Available: {available}"
            )
        return self._items[key]

    def create(self, name: str, *args: Any, **kwargs: Any) -> T:
        return self.get(name)(*args, **kwargs)

    def names(self) -> List[str]:
        self._maybe_load_entry_points()
        return sorted(self._items)

    def __contains__(self, name: str) -> bool:
        self._maybe_load_entry_points()
        return name.lower() in self._items

    def __iter__(self) -> Iterable[str]:
        return iter(self.names())

    # -- plugin discovery --------------------------------------------------
    def _maybe_load_entry_points(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:  # pragma: no cover - depends on installed third-party plugins
            from importlib.metadata import entry_points

            for ep in entry_points(group=_ENTRY_POINT_GROUP):
                if ep.name.startswith(f"{self.kind}:"):
                    _, _, target = ep.name.partition(":")
                    try:
                        self._items.setdefault(target.lower(), ep.load())
                    except Exception:  # noqa: BLE001 - plugin loading is best-effort
                        pass
        except Exception:  # noqa: BLE001
            pass


# Global registries -------------------------------------------------------
PROVIDERS: Registry[Any] = Registry("provider")
MODES: Registry[Any] = Registry("mode")
FILTERS: Registry[Any] = Registry("filter")
FORMATTERS: Registry[Any] = Registry("formatter")
EVALUATORS: Registry[Any] = Registry("evaluator")
