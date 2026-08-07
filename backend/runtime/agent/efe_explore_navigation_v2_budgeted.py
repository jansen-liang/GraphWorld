"""Independent EFE navigation v2: shortest paths with bounded exploration."""

from __future__ import annotations

import copy
from typing import Any

from backend.runtime.agent.efe_explore_navigation_v1 import (
    EfeExploreNavigationV1Loop,
    robot_room,
)


PATROL_COOLDOWN_STEPS = 30


class EfeExploreNavigationV2BudgetedLoop(EfeExploreNavigationV1Loop):
    """Prefer concrete work, explore unseen rooms, then patrol at low frequency."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._v2_concrete_goals_available = False
        self._v2_last_explore_commit = -10**9
        self._v2_stats = {
            "exploration_suppressed_by_concrete_goal": 0,
            "exploration_suppressed_by_cooldown": 0,
            "idle_anchor_actions": 0,
        }

    def _commit_goal(self, goal: dict[str, Any], step: int,
                     selected_by: str, candidate_count: int = 0) -> None:
        super()._commit_goal(goal, step, selected_by, candidate_count)
        if str(goal.get("type") or "") in {"explore", "patrol"}:
            self._v2_last_explore_commit = step

    def _exploration_goals(self, observation: dict[str, Any], step: int,
                           limit: int = 2) -> list[dict[str, Any]]:
        if self._v2_concrete_goals_available:
            self._v2_stats["exploration_suppressed_by_concrete_goal"] += 1
            return []

        current_room = robot_room(observation, self.baseline, self.agent_id)
        unseen = sorted(self._all_rooms - self._visited_rooms)
        targets = [room for room in unseen if room != current_room]
        if not targets:
            if step - self._v2_last_explore_commit < PATROL_COOLDOWN_STEPS:
                self._v2_stats["exploration_suppressed_by_cooldown"] += 1
                return []
            targets = sorted(
                (
                    room for room in self._all_rooms
                    if room != current_room
                    and step - self._room_last_visited.get(room, -10**9)
                    >= PATROL_COOLDOWN_STEPS
                ),
                key=lambda room: (self._room_last_visited.get(room, -10**9), room),
            )[:1]

        return [{
            "type": "explore",
            "task": f"explore {room}",
            "target": room,
            "room": room,
            "object_room": room,
            "target_room": room,
            "robot_room": current_room,
            "_candidate_source": "explore",
        } for room in targets[:max(0, int(limit))]]

    def _local_idle_action(
        self, observation: dict[str, Any], candidates: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        current_room = robot_room(observation, self.baseline, self.agent_id)
        visible = {
            str(node.get("id") or ""): node
            for node in observation.get("nodes") or []
            if isinstance(node, dict) and node.get("id")
        }

        def containing_room(node_id: str) -> str:
            seen: set[str] = set()
            while node_id and node_id not in seen:
                seen.add(node_id)
                node = visible.get(node_id) or {}
                if str(node.get("node_type") or "") == "room":
                    return node_id
                node_id = str(node.get("parent") or "")
            return ""

        local_moves = [
            action for action in candidates
            if str(action.get("action") or "") == "move"
            and str(action.get("target") or "") in visible
            and containing_room(str(action.get("target") or "")) == current_room
            and str((visible.get(str(action.get("target") or "")) or {}).get("node_type") or "")
            != "room"
        ]
        if not local_moves:
            return None
        selected = copy.deepcopy(min(local_moves, key=lambda action: str(action.get("target") or "")))
        selected["reason"] = "efe_explore_navigation_v2_budgeted: local idle anchor"
        return selected

    def authority_diagnostics(self) -> dict[str, Any]:
        diagnostics = super().authority_diagnostics()
        diagnostics["explore_navigation_variant"] = "efe_explore_navigation_v2_budgeted"
        diagnostics.update({f"explore_navigation_v2_{key}": value
                            for key, value in self._v2_stats.items()})
        return diagnostics

    def step(self, observation: dict[str, Any], candidates: list[dict[str, Any]],
             step: int, **kwargs: Any) -> dict[str, Any]:
        self._v2_concrete_goals_available = bool(
            kwargs.get("active_goal") or kwargs.get("pipeline_goals")
        )
        result = super().step(observation, candidates, step, **kwargs)
        if self._last_goal is None:
            idle = self._local_idle_action(observation, candidates)
            if idle is not None:
                result["action"] = idle
                self._v2_stats["idle_anchor_actions"] += 1
        result["authority_diagnostics"] = self.authority_diagnostics()
        return result
