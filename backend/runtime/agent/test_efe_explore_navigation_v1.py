from __future__ import annotations

import unittest

from backend.runtime.agent.efe_explore_navigation_v1 import (
    choose_explore_navigation_action,
    next_room_on_shortest_path,
)


def _scene() -> dict:
    return {
        "nodes": [
            {"id": "room_a", "node_type": "room"},
            {"id": "room_b", "node_type": "room"},
            {"id": "room_c", "node_type": "room"},
            {"id": "robot_01", "node_type": "robot", "parent": "room_a"},
        ],
        "edges": [
            {"source_id": "room_a", "target_id": "room_b", "relation": "connected"},
            {"source_id": "room_b", "target_id": "room_c", "relation": "connected"},
        ],
    }


class ExploreNavigationV1Test(unittest.TestCase):
    def test_shortest_path_returns_first_hop(self) -> None:
        self.assertEqual(next_room_on_shortest_path(_scene(), "room_a", "room_c"), "room_b")

    def test_explore_chooses_legal_next_room_move(self) -> None:
        action, diagnostic = choose_explore_navigation_action(
            baseline=_scene(),
            observation={"nodes": _scene()["nodes"]},
            candidates=[
                {"action": "move", "target": "irrelevant"},
                {"action": "move", "target": "room_b", "agent": "robot_01"},
            ],
            goal={"type": "explore", "target_room": "room_c"},
        )
        self.assertEqual(action["target"], "room_b")
        self.assertEqual(diagnostic["choice_kind"], "move_next_room")

    def test_non_explore_goal_is_untouched(self) -> None:
        action, diagnostic = choose_explore_navigation_action(
            baseline=_scene(), observation={"nodes": _scene()["nodes"]},
            candidates=[{"action": "move", "target": "room_b"}],
            goal={"type": "skill", "target_room": "room_c"},
        )
        self.assertIsNone(action)
        self.assertFalse(diagnostic["applicable"])

    def test_missing_legal_path_action_falls_back(self) -> None:
        action, diagnostic = choose_explore_navigation_action(
            baseline=_scene(), observation={"nodes": _scene()["nodes"]},
            candidates=[{"action": "move", "target": "irrelevant"}],
            goal={"type": "explore", "target_room": "room_c"},
        )
        self.assertIsNone(action)
        self.assertEqual(diagnostic["choice_kind"], "no_legal_path_action")


if __name__ == "__main__":
    unittest.main()
