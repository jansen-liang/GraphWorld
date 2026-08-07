from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.runtime.agent.efe_clean_entry_evidence_v1 import (
    EfeCleanEntryEvidenceV1Loop,
)


def scene() -> dict:
    return {
        "nodes": [
            {"id": "room_a", "node_type": "room"},
            {"id": "room_b", "node_type": "room"},
            {"id": "robot_01", "node_type": "robot", "parent": "room_a"},
        ],
        "edges": [
            {"source_id": "room_a", "target_id": "room_b", "relation": "connected"},
        ],
    }


class CleanEntryEvidenceV1Test(unittest.TestCase):
    def make_loop(self) -> EfeCleanEntryEvidenceV1Loop:
        environment = {
            "EFE_FORMULA_VARIANT": "stale_h005",
            "EFE_CLEAN_EVIDENCE_VARIANT": "clean_w050",
        }
        with patch.dict(os.environ, environment):
            return EfeCleanEntryEvidenceV1Loop(scene(), efe_mode="goal_conditioned")

    def test_clean_entry_updates_once_while_stationary(self) -> None:
        loop = self.make_loop()
        observation = scene()
        before = loop.world_belief["room_a"].beta
        loop._observe_clean_entry(observation, [], 0)
        loop._observe_clean_entry(observation, [], 1)
        self.assertEqual(loop.world_belief["room_a"].beta, before + 0.5)
        self.assertEqual(loop._clean_evidence_stats["clean_updates"], 1)

    def test_deviated_entry_is_not_clean_evidence(self) -> None:
        loop = self.make_loop()
        before = loop.world_belief["room_a"].beta
        loop._observe_clean_entry(
            scene(), [{"node_id": "room_a", "room": "room_a"}], 0)
        self.assertEqual(loop.world_belief["room_a"].beta, before)
        self.assertEqual(loop._clean_evidence_stats["entries_with_deviation"], 1)


if __name__ == "__main__":
    unittest.main()
