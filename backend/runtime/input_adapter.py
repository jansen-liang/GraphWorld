"""Resolve physical interaction input into canonical world actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.runtime.domain.queries import held_objects, holding, is_open, node, object_capabilities, parent_of, supports_action
from backend.runtime.agent_profile import profile_for_agent
from backend.core.input_event import InteractEvent


@dataclass(frozen=True)
class InteractionRequest:
    actor_id: str
    input: str = "interact_primary"
    target_id: str = ""
    target_link_id: str = ""
    distance_m: float | None = None
    hit: dict[str, Any] = field(default_factory=dict)
    hand: str = "right"
    event: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "InteractionRequest":
        hit = payload.get("hit") if isinstance(payload.get("hit"), dict) else {}
        return cls(
            actor_id=str(payload.get("actor_id") or payload.get("agent") or "robot_01"),
            input=str(payload.get("input") or "interact_primary"),
            target_id=str(payload.get("target_id") or payload.get("target") or hit.get("node_id") or ""),
            target_link_id=str(payload.get("target_link_id") or hit.get("link_id") or ""),
            distance_m=float(payload.get("distance_m", hit.get("distance", 0)) or 0),
            hit=dict(hit),
            hand=str(payload.get("hand") or "right"),
            event=dict(payload.get("event") or {}),
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


def _link_payload(request: InteractionRequest) -> dict[str, str]:
    return {"target_link_id": request.target_link_id} if request.target_link_id else {}


def _resolve_interaction(state: dict[str, Any], request: InteractionRequest | dict[str, Any]) -> ResolvedInteraction:
    """Resolve a player or agent interaction without mutating state.

    The resolver intentionally returns existing canonical action payloads. A
    caller may pass that payload to ``validate_action_schema`` and then apply
    it through the normal transition engine.
    """
    request = InteractionRequest.from_dict(request) if isinstance(request, dict) else request
    actor = node(state, request.actor_id)
    if not actor:
        return ResolvedInteraction(None, (f"unknown agent: {request.actor_id}",))
    if not request.target_id:
        if request.input == "lower_hand":
            return ResolvedInteraction({"agent": request.actor_id, "action": "lower_hand", "hand": request.hand})
        if request.input in {"interact_primary", "interact_secondary", "grab", "use"}:
            return ResolvedInteraction({"agent": request.actor_id, "action": "raise_hand", "hand": request.hand})
        return ResolvedInteraction(None, ("interaction target is required",))
    target = node(state, request.target_id)
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
    can_open = "openable" in capabilities or supports_action(target, "open")
    can_receive = "place_target" in capabilities or "receptacle" in capabilities or target.get("node_type") == "room"
    if held_id:
        if can_receive:
            action = {"agent": request.actor_id, "action": "place", "object": held_id, "target": request.target_id}
            action.update(_hand_payload(request.hand))
            if request.target_link_id:
                action["target_link_id"] = request.target_link_id
            action.update({key: value for key, value in request.hit.items() if key in {"surface_point_cm", "surface_anchor", "volume_anchor", "interaction_hit"}})
            if request.hit:
                action["interaction_hit"] = dict(request.hit)
            if "surface_uv" in request.hit:
                action["surface_anchor"] = request.hit["surface_uv"]
            if "volume_uv" in request.hit:
                action["volume_anchor"] = request.hit["volume_uv"]
            return ResolvedInteraction(action)
        return ResolvedInteraction(None, (f"target cannot receive held object: {request.target_id}",))
    # Hands are independent resources. A held object only blocks interactions
    # issued with that same hand; the other empty hand remains available for
    # doors, controls, and picking another one-hand object. Two-hand targets
    # are handled by the explicit requirement above.
    # A container/storage link is interacted with as a LIFO retrieval surface,
    # not as a pickable object of its own. This also keeps older materialized
    # scenes safe when a generic storage_slot template still carries the
    # pickable capability.
    if "can_contain" in capabilities or bool(target.get("can_contain")) or "receptacle" in capabilities:
        contained: list[tuple[int, str]] = []
        for edge in state.get("edges") or []:
            relation = str(edge.get("relation") or "").lower()
            if relation not in {"in", "inside", "contained_by", "on"}:
                continue
            if str(edge.get("target_id") or edge.get("target")) != request.target_id:
                continue
            item_id = str(edge.get("source_id") or edge.get("source") or "")
            item = node(state, item_id)
            if not item or item_id == request.target_id:
                continue
            inserted = edge.get("inserted_at", (edge.get("properties") or {}).get("inserted_at"))
            if inserted is None:
                inserted = item.get("inserted_at", 0)
            try:
                order = int(inserted)
            except (TypeError, ValueError):
                order = 0
            contained.append((order, item_id))
        if contained:
            _, item_id = max(contained, key=lambda value: value[0])
            action = {"agent": request.actor_id, "action": "pick", "object": item_id, "target": request.target_id}
            action.update(_hand_payload(request.hand))
            action["target_link_id"] = request.target_link_id or request.target_id
            return ResolvedInteraction(action)
    if "switchable" in capabilities or "water_source_control" in capabilities or supports_action(target, "press"):
        action = {"agent": request.actor_id, "action": "press", "target": request.target_id}
        action.update(_link_payload(request))
        return ResolvedInteraction(action)
    if "pickable" in capabilities:
        if str(target.get("node_type") or "").lower() != "object":
            return ResolvedInteraction(None, (f"target is not a pickable object: {request.target_id}",))
        action = {"agent": request.actor_id, "action": "pick", "object": request.target_id}
        action.update({"hand": "both"} if "two_hand_required" in capabilities else _hand_payload(request.hand))
        action.update(_link_payload(request))
        return ResolvedInteraction(action)
    if can_open:
        action_name = "close" if is_open(target) else "open"
        action = {"agent": request.actor_id, "action": action_name, "target": request.target_id}
        action.update(_link_payload(request))
        return ResolvedInteraction(action)
    return ResolvedInteraction(None, (f"no affordance for input {request.input}: {request.target_id}",))


class ActionResolver:
    """Pure input-to-action boundary shared by all runtime adapters."""

    def resolve(self, state: dict[str, Any], request: InteractionRequest | InteractEvent | dict[str, Any]) -> ResolvedInteraction:
        if isinstance(request, InteractEvent):
            hit: dict[str, Any] = dict(request.parameters)
            if request.hit_point is not None:
                hit["point_cm"] = list(request.hit_point)
            if request.hit_normal is not None:
                hit["normal"] = list(request.hit_normal)
            request = InteractionRequest(
                actor_id=request.actor_id,
                input="interact_primary" if request.input == "interact" else request.input,
                target_id=str(request.target_node_id or ""),
                target_link_id=str(request.target_link_id or ""),
                hit=hit,
                hand=request.hand,
            )
        return _resolve_interaction(state, request)


action_resolver = ActionResolver()


def resolve_interaction(state: dict[str, Any], request: InteractionRequest | dict[str, Any]) -> ResolvedInteraction:
    """Compatibility function delegating to the canonical resolver object."""
    return action_resolver.resolve(state, request)


__all__ = ["ActionResolver", "action_resolver", "InteractionRequest", "ResolvedInteraction", "resolve_interaction"]
