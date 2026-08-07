"""Isolated goal-conditioned experiment with a non-mutating maintain action."""

from __future__ import annotations

import copy
from typing import Any

from backend.runtime.agent.efe_explore_navigation_v1 import (
    EfeExploreNavigationV1Loop,
    robot_room,
)


def choose_safe_maintain_action(
    *,
    baseline: dict[str, Any],
    observation: dict[str, Any],
    candidates: list[dict[str, Any]],
    agent_id: str = "robot_01",
) -> dict[str, Any] | None:
    """Choose a legal move to a fixed local anchor; never pick/place an object."""
    current_room = robot_room(observation, baseline, agent_id)
    nodes: dict[str, dict[str, Any]] = {}
    for source in (baseline, observation):
        for node in source.get("nodes") or []:
            if isinstance(node, dict) and node.get("id"):
                nodes[str(node["id"])] = node

    def room_of(node_id: str) -> str:
        seen: set[str] = set()
        while node_id and node_id not in seen:
            seen.add(node_id)
            node = nodes.get(node_id) or {}
            if str(node.get("node_type") or "") == "room":
                return node_id
            node_id = str(node.get("parent") or "")
        return ""

    local_moves: list[tuple[int, str, dict[str, Any]]] = []
    for candidate in candidates:
        if str(candidate.get("action") or "") != "move":
            continue
        target = str(candidate.get("target") or "")
        node = nodes.get(target) or {}
        if room_of(target) != current_room:
            continue
        if str(node.get("node_type") or "") not in {"fixed_object", "control_object"}:
            continue
        semantic = str(node.get("semantic_type") or "")
        # Room lights/buttons are passive anchors in this experiment; doors
        # and task containers are deliberately lower priority.
        priority = 0 if semantic == "room_light" else (1 if semantic == "button" else 2)
        local_moves.append((priority, target, candidate))
    if not local_moves:
        return None
    _, _, selected = min(local_moves, key=lambda item: (item[0], item[1]))
    action = copy.deepcopy(selected)
    action["reason"] = "efe_goal_conditioned_safe_maintain_v1: local fixed anchor"
    return action


class EfeGoalConditionedSafeMaintainV1Loop(EfeExploreNavigationV1Loop):
    """Shortest-path EFE whose maintain goal cannot mutate movable objects."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._safe_maintain_actions = 0
        self._safe_maintain_fallbacks = 0

    def authority_diagnostics(self) -> dict[str, Any]:
        diagnostics = super().authority_diagnostics()
        diagnostics.update({
            "safe_maintain_variant": "efe_goal_conditioned_safe_maintain_v1",
            "safe_maintain_actions": self._safe_maintain_actions,
            "safe_maintain_fallbacks": self._safe_maintain_fallbacks,
        })
        return diagnostics

    def step(self, observation: dict[str, Any], candidates: list[dict[str, Any]],
             step: int, **kwargs: Any) -> dict[str, Any]:
        result = super().step(observation, candidates, step, **kwargs)
        held_type = str((self._last_goal or {}).get("type") or "")
        if held_type in {"maintain", "idle", "wait"}:
            safe_action = choose_safe_maintain_action(
                baseline=self.baseline,
                observation=observation,
                candidates=candidates,
                agent_id=self.agent_id,
            )
            if safe_action is not None:
                result["action"] = safe_action
                self._safe_maintain_actions += 1
            else:
                self._safe_maintain_fallbacks += 1
        result["authority_diagnostics"] = self.authority_diagnostics()
        return result
