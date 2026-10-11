"""Exception hierarchy for the distill framework."""

from __future__ import annotations


class DistillError(Exception):
    """Base class for all framework errors."""


class ProviderError(DistillError):
    """Raised when a teacher/student provider fails to produce a result."""


class ConfigError(DistillError):
    """Raised when a run configuration is invalid."""


class RegistryError(DistillError):
    """Raised on missing/duplicate registry entries."""


class MissingDependencyError(DistillError):
    """Raised when an optional dependency required by a component is absent."""

    def __init__(self, package: str, feature: str) -> None:
        super().__init__(
            f"Optional dependency '{package}' is required for {feature}. "
            f"Install it with: pip install 'distill[{feature}]' or pip install {package}"
        )
        self.package = package
        self.feature = feature


class ToolExecutionError(DistillError):
    """Raised when a tool invoked by an agent fails."""


class FilterRejection(DistillError):
    """Raised inside a filter to signal a sample should be dropped."""
