"""Data-driven elevator scheduling and door-cycle rules.

The elevator remains an ordinary Object node.  This module only advances the
state declared by a transport device and therefore can be used by any runtime
adapter without introducing an elevator-specific world type.
"""

from __future__ import annotations

from typing import Any


def _state(node: dict[str, Any]) -> dict[str, Any]:
    return node.setdefault("states", {})


def enqueue_request(node: dict[str, Any], floor_id: str, request_kind: str = "cabin", *, step: int = 0) -> bool:
    """Add or merge a stop request, preserving its source kind."""
    floor_id = str(floor_id or "")
    if not floor_id:
        return False
    queue = node.setdefault("request_queue", [])
    for request in queue:
        if str(request.get("floor_id") or "") == floor_id:
            kinds = set(request.get("kinds") or ())
            kinds.add(str(request_kind or "cabin"))
            request["kinds"] = sorted(kinds)
            return False
    queue.append({"floor_id": floor_id, "kinds": [str(request_kind or "cabin")], "created_at": int(step)})
    return True


def _ordered_floor_ids(node: dict[str, Any]) -> list[str]:
    configured = node.get("floor_ids") or node.get("served_floors") or node.get("served_rooms") or ()
    return [str(value) for value in configured]


def _floor_index(node: dict[str, Any], floor_id: str) -> int:
    floors = _ordered_floor_ids(node)
    try:
        return floors.index(str(floor_id))
    except ValueError:
        return 0


def _elevation(node: dict[str, Any], floor_id: str) -> float:
    """Return configured height, or a deterministic one-floor fallback."""
    elevations = node.get("floor_elevations") or node.get("elevations") or {}
    try:
        if str(floor_id) in elevations:
            return float(elevations[str(floor_id)])
    except (TypeError, ValueError):
        pass
    return float(_floor_index(node, str(floor_id))) * float(node.get("floor_height_m") or 3.2)


def _choose_direction(node: dict[str, Any]) -> str:
    state = _state(node)
    current = _floor_index(node, str(state.get("current_floor") or _ordered_floor_ids(node)[0] if _ordered_floor_ids(node) else ""))
    queue = node.get("request_queue") or []
    if not queue:
        return "idle"
    # Arrival order chooses the first direction. If requests are simultaneous
    # (same timestamp), up wins deterministically.
    first = min(queue, key=lambda item: (int(item.get("created_at") or 0), 0 if _floor_index(node, str(item.get("floor_id"))) >= current else 1))
    target = _floor_index(node, str(first.get("floor_id")))
    return "up" if target >= current else "down"


def advance_elevator(node: dict[str, Any], elapsed_steps: int = 1, *, step: int = 0) -> list[dict[str, Any]]:
    """Advance one elevator by discrete runtime ticks.

    A tick is intentionally coarse: the frontend animates the car and doors
    from the state/joint snapshot. Semantic door access changes happen at the
    beginning of opening and closing, independent of animation completion.
    """
    if "transport_device" not in {str(value).lower() for value in (node.get("capabilities") or ())}:
        return []
    floors = _ordered_floor_ids(node)
    if not floors:
        return []
    state = _state(node)
    state.setdefault("current_floor", floors[0])
    state.setdefault("direction", "idle")
    state.setdefault("motion_state", "idle")
    state.setdefault("door_phase", "closed")
    state.setdefault("is_open", False)
    state.setdefault("dwell_remaining", 0)
    # The floor id is semantic state; the height is the continuous transport
    # state consumed by renderers. Keep both so a car never teleports or loses
    # its authored XY anchor while travelling between stops.
    current_elevation = _elevation(node, str(state.get("current_floor")))
    state.setdefault("current_height", current_elevation)
    state.setdefault("target_height", current_elevation)
    events: list[dict[str, Any]] = []
    for _ in range(max(0, int(elapsed_steps))):
        phase = str(state.get("door_phase") or "closed")
        queue = node.setdefault("request_queue", [])
        current = str(state.get("current_floor") or floors[0])
        if phase == "closing":
            if any(str(item.get("floor_id") or "") == current for item in queue):
                state["door_phase"] = "dwelling"
                state["is_open"] = True
                state["dwell_remaining"] = 2
                events.append({"type": "elevator_door_reopened", "elevator_id": node.get("id"), "floor_id": current})
            else:
                state["door_phase"] = "closed"
                state["is_open"] = False
                state["motion_state"] = "idle"
            continue
        if phase == "dwelling":
            state["dwell_remaining"] = max(0, int(state.get("dwell_remaining") or 0) - 1)
            if any(str(item.get("floor_id") or "") == current for item in queue):
                state["dwell_remaining"] = 2
            if int(state["dwell_remaining"]) <= 0:
                state["door_phase"] = "closing"
                state["is_open"] = False
                events.append({"type": "elevator_doors_closing", "elevator_id": node.get("id"), "floor_id": current})
            continue
        if phase == "opening":
            state["door_phase"] = "dwelling"
            state["is_open"] = True
            state["dwell_remaining"] = 2
            continue
        if phase != "closed":
            continue
        if str(state.get("motion_state") or "") == "moving":
            target_height = float(state.get("target_height") or state.get("current_height") or 0.0)
            current_height = float(state.get("current_height") or 0.0)
            # One floor per runtime tick is deliberately deterministic. A
            # renderer may interpolate snapshots, while runtime remains the
            # authority for whether the car has reached a stop.
            delta = target_height - current_height
            speed = max(0.1, float(node.get("speed_m_per_step") or 6.4))
            if abs(delta) <= speed + 1e-6:
                state["current_height"] = target_height
                state["current_floor"] = str(state.get("target_floor") or state.get("current_floor"))
                state["motion_state"] = "stopped"
                current = str(state.get("current_floor") or floors[0])
                queue = node.setdefault("request_queue", [])
                target = next((item for item in queue if str(item.get("floor_id") or "") == current), None)
                if target:
                    node["request_queue"] = [item for item in queue if str(item.get("floor_id")) != current]
                state["door_phase"] = "opening"
                state["is_open"] = True
                events.append({"type": "elevator_arrived", "elevator_id": node.get("id"), "floor_id": current, "served_kinds": (target or {}).get("kinds", [])})
            else:
                state["current_height"] = current_height + (speed if delta > 0 else -speed)
            continue
        if not queue:
            state["direction"] = "idle"
            state["motion_state"] = "idle"
            continue
        direction = str(state.get("direction") or "idle")
        if direction == "idle":
            direction = _choose_direction(node)
            state["direction"] = direction
        current_index = _floor_index(node, current)
        candidates = [item for item in queue if (direction == "up" and _floor_index(node, str(item.get("floor_id"))) >= current_index) or (direction == "down" and _floor_index(node, str(item.get("floor_id"))) <= current_index)]
        if not candidates:
            state["direction"] = "down" if direction == "up" else "up"
            continue
        target = min(candidates, key=lambda item: _floor_index(node, str(item.get("floor_id")))) if direction == "up" else max(candidates, key=lambda item: _floor_index(node, str(item.get("floor_id"))))
        target_floor = str(target.get("floor_id"))
        if target_floor == current:
            node["request_queue"] = [item for item in queue if str(item.get("floor_id")) != current]
            state["door_phase"] = "opening"
            state["is_open"] = True
            state["motion_state"] = "stopped"
            events.append({"type": "elevator_arrived", "elevator_id": node.get("id"), "floor_id": current, "served_kinds": target.get("kinds", [])})
            continue
        # Travel directly toward the nearest queued stop in the current
        # direction. Intermediate floors without a request must not become
        # artificial stops.
        next_index = current_index + (1 if direction == "up" else -1)
        next_floor = floors[max(0, min(len(floors) - 1, next_index))]
        state["target_floor"] = target_floor
        state["target_height"] = _elevation(node, str(state["target_floor"]))
        state["motion_state"] = "moving"
        node["car_transform_progress"] = float(node.get("car_transform_progress") or 0.0) + 1.0
    return events


def advance_elevators(state: dict[str, Any], elapsed_steps: int = 1) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    nodes = state.get("nodes") or {}
    for node in nodes.values():
        if "transport_device" not in {str(value).lower() for value in (node.get("capabilities") or ())}:
            continue
        events.extend(advance_elevator(node, elapsed_steps, step=int((state.get("world_state") or {}).get("step") or 0)))
        states = _state(node)
        current_floor = str(states.get("current_floor") or "")
        served_now = any(
            event.get("type") == "elevator_arrived"
            and str(event.get("floor_id") or "") == current_floor
            for event in events
            if str(event.get("elevator_id") or "") == str(node.get("id") or "")
        )
        passable = str(states.get("door_phase") or "") in {"opening", "dwelling"} or bool(states.get("is_open"))
        # The hall doors are ordinary Door nodes. Their state is derived from
        # the same elevator process, so the renderer and room accessibility do
        # not need a second elevator-specific truth.
        for hall_door in nodes.values():
            if str(hall_door.get("door_kind") or "") != "elevator_hall":
                continue
            connected = {str(value) for value in (hall_door.get("connected_rooms") or ())}
            floor_id = str(hall_door.get("floor_id") or "")
            if not floor_id:
                door_id = str(hall_door.get("id") or "")
                for edge in state.get("edges") or []:
                    if str(edge.get("source_id") or "") != door_id or str(edge.get("relation") or "") != "connects":
                        continue
                    candidate = str(edge.get("target_id") or "")
                    if candidate in {str(value) for value in (node.get("served_rooms") or ())}:
                        floor_id = candidate
                        connected.add(candidate)
                        break
            if not floor_id:
                for room_id in connected:
                    if room_id == current_floor or room_id in {str(value) for value in (node.get("served_rooms") or ())}:
                        if room_id == current_floor:
                            floor_id = room_id
                            break
            # Only the landing currently served by the car follows the cabin
            # door phase. All other hall doors are closed and collidable as
            # soon as the car leaves their floor.
            door_open = bool(floor_id and floor_id == current_floor and passable)
            hall_door.setdefault("states", {})["is_open"] = door_open
            hall_id = str(hall_door.get("id") or "")
            hall_door["joint_states"] = {
                hall_id: door_open,
                f"{hall_id}.left": door_open,
                f"{hall_id}.right": door_open,
            }
        # Clear every cabin/hall request button for the floor just served.
        # Buttons on other floors remain lit while their request is queued.
        for button in nodes.values():
            if str(button.get("semantic_type") or "").lower() != "button":
                continue
            request_floor = str(button.get("request_floor") or "")
            if served_now and request_floor == current_floor:
                button.setdefault("states", {})["is_on"] = False
        node["joint_states"] = {
            f"{node.get('id')}.car_door_left": passable,
            f"{node.get('id')}.car_door_right": passable,
        }
    state.setdefault("world_state", {}).setdefault("event_log", []).extend(events)
    return events


__all__ = ["advance_elevator", "advance_elevators", "enqueue_request"]
