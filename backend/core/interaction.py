"""Resolve physical interaction input into canonical world actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .predicates import held_objects, holding, is_open, node, object_capabilities, parent_of, supports_action
from .agent import profile_for_agent


@dataclass(frozen=True)
class InteractionRequest:
    actor_id: str
    input: str = "interact_primary"
    target_id: str = ""
    distance_m: float | None = None
    hit: dict[str, Any] = field(default_factory=dict)
    hand: str = "right"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "InteractionRequest":
        hit = payload.get("hit") if isinstance(payload.get("hit"), dict) else {}
        return cls(
            actor_id=str(payload.get("actor_id") or payload.get("agent") or "robot_01"),
            input=str(payload.get("input") or "interact_primary"),
            target_id=str(payload.get("target_id") or payload.get("target") or hit.get("node_id") or ""),
            distance_m=float(payload.get("distance_m", hit.get("distance", 0)) or 0),
            hit=dict(hit),
            hand=str(payload.get("hand") or "right"),
        )


@dataclass(frozen=True)
class ResolvedInteraction:
    action: dict[str, Any] | None
    failures: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()


def _can_reach(request: InteractionRequest, actor: dict[str, Any]) -> str | None:
    if request.distance_m is None or request.distance_m <= 0:
        return None
    reach = float(actor.get("reach_distance_m") or actor.get("reach_m") or 2.2)
    return None if request.distance_m <= reach else f"target is out of reach: {request.distance_m:.2f}m > {reach:.2f}m"


def _hand_payload(hand: str) -> dict[str, str]:
    normalized = str(hand or "right").lower()
    return {} if normalized in {"right", "primary"} else {"hand": normalized}


def resolve_interaction(state: dict[str, Any], request: InteractionRequest | dict[str, Any]) -> ResolvedInteraction:
    """Resolve a player or agent interaction without mutating state.

    The resolver intentionally returns existing canonical action payloads. A
    caller may pass that payload to ``validate_action_schema`` and then apply
    it through the normal transition engine.
    """
    request = InteractionRequest.from_dict(request) if isinstance(request, dict) else request
    actor = node(state, request.actor_id)
    target = node(state, request.target_id)
    if not actor:
        return ResolvedInteraction(None, (f"unknown agent: {request.actor_id}",))
    if not target:
        return ResolvedInteraction(None, (f"unknown interaction target: {request.target_id}",))
    if request.input not in {"interact_primary", "interact_secondary", "grab", "release", "use", "move"}:
        return ResolvedInteraction(None, (f"unsupported interaction input: {request.input}",))
    if request.input == "move":
        if str(target.get("node_type") or "") != "room":
            return ResolvedInteraction(None, (f"move target is not a room: {request.target_id}",))
        return ResolvedInteraction({"agent": request.actor_id, "action": "move", "target": request.target_id})
    if (failure := _can_reach(request, actor)):
        return ResolvedInteraction(None, (failure,))

    occupied_hands = held_objects(state, request.actor_id)
    held_id = holding(state, request.actor_id, request.hand)
    capabilities = object_capabilities(target)
    target_states = target.get("states") or {}
    profile = profile_for_agent(actor)
    if "two_hand_required" in capabilities and profile.hand_count < 2:
        return ResolvedInteraction(None, (f"interaction requires two hands: {request.target_id}",))
    if "two_hand_required" in capabilities and occupied_hands:
        return ResolvedInteraction(None, (f"both hands must be free: {request.target_id}",))
    if request.input == "release":
        if not held_id:
            return ResolvedInteraction(None, (f"{request.hand} hand is empty",))
        action = {"agent": request.actor_id, "action": "release", "object": held_id}
        action.update(_hand_payload(request.hand))
        return ResolvedInteraction(action)
    if "switchable" in capabilities or "water_source_control" in capabilities:
        return ResolvedInteraction({"agent": request.actor_id, "action": "press", "target": request.target_id})
    can_open = "openable" in capabilities or supports_action(target, "open")
    can_receive = "place_target" in capabilities or "receptacle" in capabilities or target.get("node_type") == "room"
    if can_open and (str(target.get("semantic_type") or "") == "door" or not can_receive):
        action_name = "close" if is_open(target) else "open"
        return ResolvedInteraction({"agent": request.actor_id, "action": action_name, "target": request.target_id})
    if held_id:
        if can_receive:
            action = {"agent": request.actor_id, "action": "place", "object": held_id, "target": request.target_id}
            action.update(_hand_payload(request.hand))
            action.update({key: value for key, value in request.hit.items() if key in {"surface_point_cm", "surface_anchor", "volume_anchor", "interaction_hit"}})
            if request.hit:
                action["interaction_hit"] = dict(request.hit)
            if "surface_uv" in request.hit:
                action["surface_anchor"] = request.hit["surface_uv"]
            if "volume_uv" in request.hit:
                action["volume_anchor"] = request.hit["volume_uv"]
            return ResolvedInteraction(action)
        return ResolvedInteraction(None, (f"target cannot receive held object: {request.target_id}",))
    if can_open:
        action_name = "close" if is_open(target) else "open"
        return ResolvedInteraction({"agent": request.actor_id, "action": action_name, "target": request.target_id})
    if request.input == "grab" and "pickable" in capabilities:
        action = {"agent": request.actor_id, "action": "pick", "object": request.target_id}
        action.update({"hand": "both"} if "two_hand_required" in capabilities else _hand_payload(request.hand))
        return ResolvedInteraction(action)
    if "pickable" in capabilities:
        action = {"agent": request.actor_id, "action": "pick", "object": request.target_id}
        action.update({"hand": "both"} if "two_hand_required" in capabilities else _hand_payload(request.hand))
        return ResolvedInteraction(action)
    return ResolvedInteraction(None, (f"no affordance for input {request.input}: {request.target_id}",))


__all__ = ["InteractionRequest", "ResolvedInteraction", "resolve_interaction"]
