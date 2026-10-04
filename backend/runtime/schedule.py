from __future__ import annotations

from typing import Any

from backend.generation.assets.npc_library import planned_activity

def planned_event_for_actor(scene: dict[str, Any], actor: dict[str, Any], step: int) -> str:
    world = scene.get("world_state") or {}
    schedule_mode = str(world.get("schedule_mode") or "fixed")
    elapsed_minute = step * int(world.get("minutes_per_step") or 10)
    start_minute = int(world.get("time_min") or 0)
    absolute_minute = start_minute + elapsed_minute
    if schedule_mode == "fixed":
        minute = absolute_minute
        day = int(world.get("day") or 1)
    else:
        minute = absolute_minute % (24 * 60)
        day = int(world.get("day") or 1) + absolute_minute // (24 * 60)
    schedule_seed = int(world.get("schedule_seed") or 0)
    role = str(actor.get("role") or (actor.get("states") or {}).get("role") or "resident")
    _, _, activity = planned_activity(
        role,
        minute,
        day,
        schedule_mode=schedule_mode,
        schedule_seed=schedule_seed,
        actor_id=str(actor.get("id") or ""),
    )
    return activity


def planned_event_for_step(scene: dict[str, Any], step: int) -> str:
    actors = [node for node in scene.get("nodes") or [] if str(node.get("node_type") or "") == "agent" and str(node.get("semantic_type") or "") in {"human", "npc"}]
    if not actors:
        return ""
    return planned_event_for_actor(scene, actors[0], step)


def planned_events_for_step(scene: dict[str, Any], step: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for actor in scene.get("nodes") or []:
        if str(actor.get("node_type") or "") != "agent" or str(actor.get("semantic_type") or "") not in {"human", "npc"}:
            continue
        actor_id = str(actor.get("id") or "")
        if not actor_id:
            continue
        event_id = planned_event_for_actor(scene, actor, step)
        previous_id = planned_event_for_actor(scene, actor, step - 1) if step > 0 else ""
        next_id = planned_event_for_actor(scene, actor, step + 1)
        events.append(
            {
                "event": event_id,
                "actor": actor_id,
                "period_start": step == 0 or previous_id != event_id,
                "period_end": next_id != event_id,
            }
        )
    return events


def expected_events(scene: dict[str, Any], steps: int) -> tuple[str, ...]:
    if not any(str(node.get("node_type") or "") == "agent" and str(node.get("semantic_type") or "") in {"human", "npc"} for node in scene.get("nodes") or []):
        return ()
    events = []
    for step in range(steps):
        for event in planned_events_for_step(scene, step):
            event_id = str(event.get("event") or "")
            if event_id and event_id not in events:
                events.append(event_id)
    return tuple(events)
