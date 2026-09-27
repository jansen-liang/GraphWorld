from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.core.actions import validate_action_schema


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    failures: tuple[str, ...] = ()

    @property
    def reason(self) -> str:
        return "; ".join(self.failures)


def validate_action(state: dict[str, Any], action: dict[str, Any]) -> ValidationResult:
    failures = validate_action_schema(state, action)
    return ValidationResult(not failures, tuple(failures))


__all__ = ["ValidationResult", "validate_action"]
