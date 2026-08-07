"""Independent clean-room entry evidence experiment.

A clean observation updates the room Beta belief only when the robot physically
enters that room.  Repeated frames while stationary and rapid re-entry within
the fixed decorrelation window do not create duplicate evidence.
"""

from __future__ import annotations

import os
from typing import Any

from backend.runtime.agent.efe_explore_navigation_v1 import robot_room
from backend.runtime.agent.efe_formula_staleness_v1 import EfeFormulaStalenessV1Loop


CLEAN_EVIDENCE_WEIGHTS = {
    "none": 0.0,
    "clean_w025": 0.25,
    "clean_w050": 0.50,
    "clean_w100": 1.00,
}
MIN_REOBSERVATION_STEPS = 5


def deviation_room(
    deviation: dict[str, Any], observation: dict[str, Any]
) -> str:
    """Resolve a deviation's room from its explicit field or visible parents."""
    explicit = str(deviation.get("room") or "")
    if explicit:
        return explicit
    nodes = {
        str(node.get("id") or ""): node
        for node in observation.get("nodes") or []
        if isinstance(node, dict) and node.get("id")
    }
    current = str(deviation.get("node_id") or "")
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        node = nodes.get(current) or {}
        if str(node.get("node_type") or "") == "room":
            return current
        current = str(node.get("parent") or "")
    return ""


class EfeCleanEntryEvidenceV1Loop(EfeFormulaStalenessV1Loop):
    """Staleness EFE with one data-driven clean Beta update per room entry."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.clean_evidence_variant = os.environ.get(
            "EFE_CLEAN_EVIDENCE_VARIANT", "none")
        if self.clean_evidence_variant not in CLEAN_EVIDENCE_WEIGHTS:
            raise ValueError(
                f"unsupported clean evidence variant: {self.clean_evidence_variant}")
        self.clean_evidence_weight = CLEAN_EVIDENCE_WEIGHTS[
            self.clean_evidence_variant]
        self._clean_entry_last_room = ""
        self._clean_evidence_last_step: dict[str, int] = {}
        self._clean_evidence_stats = {
            "room_entries": 0,
            "clean_updates": 0,
            "entries_with_deviation": 0,
            "decorrelation_skips": 0,
        }
        super().__init__(*args, **kwargs)

    def _observe_clean_entry(
        self,
        observation: dict[str, Any],
        deviations: list[dict[str, Any]],
        step: int,
    ) -> None:
        room = robot_room(observation, self.baseline, self.agent_id)
        if not room or room == self._clean_entry_last_room:
            return
        self._clean_entry_last_room = room
        self._clean_evidence_stats["room_entries"] += 1

        if any(deviation_room(item, observation) == room for item in deviations):
            self._clean_evidence_stats["entries_with_deviation"] += 1
            return
        if self.clean_evidence_weight <= 0.0:
            return
        last_step = self._clean_evidence_last_step.get(room, -10**9)
        if step - last_step < MIN_REOBSERVATION_STEPS:
            self._clean_evidence_stats["decorrelation_skips"] += 1
            return

        evidence_key = f"clean_entry:{room}:{step}"
        if self.world_belief.update(
            room,
            "refute",
            self.clean_evidence_weight,
            evidence_key=evidence_key,
            step=step,
        ):
            self._clean_evidence_last_step[room] = step
            self._clean_evidence_stats["clean_updates"] += 1

    def authority_diagnostics(self) -> dict[str, Any]:
        diagnostics = super().authority_diagnostics()
        diagnostics.update({
            "clean_evidence_variant": self.clean_evidence_variant,
            "clean_evidence_weight": self.clean_evidence_weight,
            "clean_evidence_min_reobservation_steps": MIN_REOBSERVATION_STEPS,
            **{
                f"clean_evidence_{key}": value
                for key, value in self._clean_evidence_stats.items()
            },
        })
        return diagnostics

    def step(self, observation: dict[str, Any], candidates: list[dict[str, Any]],
             step: int, **kwargs: Any) -> dict[str, Any]:
        deviations = list(kwargs.get("deviations") or [])
        self._observe_clean_entry(observation, deviations, int(step))
        result = super().step(observation, candidates, step, **kwargs)
        result["authority_diagnostics"] = self.authority_diagnostics()
        return result


__all__ = [
    "CLEAN_EVIDENCE_WEIGHTS",
    "EfeCleanEntryEvidenceV1Loop",
    "MIN_REOBSERVATION_STEPS",
    "deviation_room",
]
