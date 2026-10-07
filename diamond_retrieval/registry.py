"""Explicit registries with strict, unambiguous support matching."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TypeVar

from .errors import AmbiguousRegistrationError, ConfigurationError

T = TypeVar("T")


def select_unique(components: Iterable[T], value: Any, *, role: str) -> T | None:
    matches: list[T] = []
    for component in components:
        try:
            supported = component.supports(value)  # type: ignore[attr-defined]
        except Exception as exc:
            raise ConfigurationError(
                f"{role} {type(component).__name__}.supports() failed: {exc}"
            ) from exc
        if supported:
            matches.append(component)
    if len(matches) > 1:
        names = ", ".join(type(component).__name__ for component in matches)
        raise AmbiguousRegistrationError(
            f"Ambiguous {role} registration for input: {names}"
        )
    return matches[0] if matches else None
