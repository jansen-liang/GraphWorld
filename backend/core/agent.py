"""Agent embodiment contract shared by player, robot, and NPC controllers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentProfile:
    collision_shape: str = "capsule"
    height_m: float = 1.6
    radius_m: float = 0.28
    reach_distance_m: float = 2.2
    hand_count: int = 2
    hand_capabilities: tuple[str, ...] = ("grasp", "place", "use")
    two_hand_capabilities: tuple[str, ...] = ("carry_large", "two_hand_manipulation")

    def to_dict(self) -> dict[str, Any]:
        return {
            "collision_shape": self.collision_shape,
            "height_m": self.height_m,
            "radius_m": self.radius_m,
            "reach_distance_m": self.reach_distance_m,
            "hand_count": self.hand_count,
            "hand_capabilities": list(self.hand_capabilities),
            "two_hand_capabilities": list(self.two_hand_capabilities),
        }


DEFAULT_AGENT_PROFILE = AgentProfile()


def profile_for_agent(agent: dict[str, Any]) -> AgentProfile:
    geometry = agent.get("geometry") if isinstance(agent.get("geometry"), dict) else {}
    return AgentProfile(
        collision_shape=str(geometry.get("collision_shape") or agent.get("collision_shape") or "capsule"),
        height_m=float(geometry.get("height_m") or agent.get("height_m") or 1.6),
        radius_m=float(geometry.get("radius_m") or agent.get("radius_m") or 0.28),
        reach_distance_m=float(agent.get("reach_distance_m") or 2.2),
        hand_count=max(1, int(agent.get("hand_count") or 2)),
        hand_capabilities=tuple(str(item) for item in agent.get("hand_capabilities") or DEFAULT_AGENT_PROFILE.hand_capabilities),
        two_hand_capabilities=tuple(str(item) for item in agent.get("two_hand_capabilities") or DEFAULT_AGENT_PROFILE.two_hand_capabilities),
    )


__all__ = ["AgentProfile", "DEFAULT_AGENT_PROFILE", "profile_for_agent"]
