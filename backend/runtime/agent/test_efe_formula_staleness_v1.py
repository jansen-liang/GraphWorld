from __future__ import annotations

import unittest

from backend.runtime.agent.efe_formula_staleness_v1 import (
    NoMaintainLearningGoalOutcomeModel,
    formula_decomposition,
    predicted_room_risk,
    room_observation_information_gain,
)


class FormulaStalenessV1Test(unittest.TestCase):
    def test_process_noise_moves_certain_belief_toward_uncertainty(self) -> None:
        now = predicted_room_risk(0.05, 0, 0.02)
        stale = predicted_room_risk(0.05, 50, 0.02)
        self.assertLess(now, stale)
        self.assertLess(stale, 0.5)
        self.assertGreater(
            room_observation_information_gain(stale),
            room_observation_information_gain(now),
        )

    def test_null_action_has_zero_score(self) -> None:
        result = formula_decomposition(
            {"type": "maintain", "task": "maintain_order"}, [],
            variant="null_fixed", outcome_model=NoMaintainLearningGoalOutcomeModel(),
        )
        self.assertEqual(result["G"], 0.0)

    def test_maintain_does_not_update_success_posterior(self) -> None:
        model = NoMaintainLearningGoalOutcomeModel()
        before = model.belief("maintain").to_dict()
        model.update({"type": "maintain"}, "completed", 1)
        self.assertEqual(before, model.belief("maintain").to_dict())


if __name__ == "__main__":
    unittest.main()
