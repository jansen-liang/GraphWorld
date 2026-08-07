"""Independent clean-entry evidence variants for B-learning experiments v2.

This file deliberately does not modify the v1 experiment.  A clean room is
counted once on physical entry, with a short decorrelation window, and updates
the room Beta belief with a configured fractional evidence weight.
"""

from __future__ import annotations

import os
from typing import Any

from backend.runtime.agent.efe_clean_entry_evidence_v1 import deviation_room
from backend.runtime.agent.efe_explore_navigation_v1 import robot_room
from backend.runtime.agent.efe_formula_staleness_v1 import EfeFormulaStalenessV1Loop


CLEAN_EVIDENCE_WEIGHTS_V2 = {
    "none": 0.0,
    "clean_w050": 0.50,
    "clean_w075": 0.75,
    "clean_w100": 1.00,
    "clean_w125": 1.25,
}
MIN_REOBSERVATION_STEPS_V2 = 5


class EfeCleanEntryBLearningV2Loop(EfeFormulaStalenessV1Loop):
    """Goal-conditioned-B loop with auditable clean-entry observations."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.clean_evidence_variant = os.environ.get(
            "EFE_CLEAN_EVIDENCE_VARIANT", "none")
        if self.clean_evidence_variant not in CLEAN_EVIDENCE_WEIGHTS_V2:
            raise ValueError(
                f"unsupported v2 clean evidence variant: "
                f"{self.clean_evidence_variant}")
        self.clean_evidence_weight = CLEAN_EVIDENCE_WEIGHTS_V2[
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
        if step - last_step < MIN_REOBSERVATION_STEPS_V2:
            self._clean_evidence_stats["decorrelation_skips"] += 1
            return

        evidence_key = f"clean_entry_b_v2:{room}:{step}"
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
            "clean_evidence_experiment": "efe_clean_entry_b_learning_v2",
            "clean_evidence_variant": self.clean_evidence_variant,
            "clean_evidence_weight": self.clean_evidence_weight,
            "clean_evidence_min_reobservation_steps":
                MIN_REOBSERVATION_STEPS_V2,
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
    "CLEAN_EVIDENCE_WEIGHTS_V2",
    "EfeCleanEntryBLearningV2Loop",
    "MIN_REOBSERVATION_STEPS_V2",
]
