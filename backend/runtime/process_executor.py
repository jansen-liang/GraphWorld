"""Runtime owner for long-running processes.

Process definitions are data-driven; device-specific behavior belongs in
templates and transition profiles, not in the core action vocabulary.
"""

from __future__ import annotations

from typing import Any

from backend.runtime.process_rules import apply_timed_transitions


class ProcessExecutor:
    def __init__(self, world):
        self.world = world

    def advance(self, elapsed_steps: int = 1) -> list[str]:
        return apply_timed_transitions(self.world.state_for_rules(), elapsed_steps=elapsed_steps)


__all__ = ["ProcessExecutor"]
