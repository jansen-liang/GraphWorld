"""Unified passive rules, timed transitions, and device processes.

Processes are intentionally stored in world state so they survive replay and
can be inspected by planners.  Object placement remains the source of truth
for recipe inputs; this module only schedules and commits the transition.
"""

from typing import Any

from backend.generation.assets.object_library import PROCESS_DEFINITIONS, build_object_node
from backend.runtime.process_definitions import PROCESS_WATER_COST
from backend.runtime.domain.queries import (
    children_of,
    descendants_of,
    mutable_states,
    node,
    object_capabilities,
    object_property,
    parent_of,
    semantic,
)
from backend.core.edge import move_position_in_state as move_position
from backend.core.state import DiscreteState
from backend.runtime.process_profiles import (
    apply_effects,
    contained_profile,
    contextual_duration,
    profile_duration,
    temporal_effects,
)
from backend.runtime.elevator import advance_elevators

RECIPE_SPECS = PROCESS_DEFINITIONS


def process_definition(device: dict[str, Any]) -> dict[str, Any]:
    """Read a process contract from capability materialized node data."""
    definition = device.get("process_definition")
    if isinstance(definition, dict):
        return definition
    capabilities = device.get("capability_properties") or {}
    definition = capabilities.get("process_definition") if isinstance(capabilities, dict) else None
    if isinstance(definition, dict):
        return definition
    # Compatibility for older snapshots that contain only semantic_type. The
    # canonical source remains the template's capability declaration.
    try:
        from backend.generation.assets.object_library import OBJECT_LIBRARY
        template = OBJECT_LIBRARY.get(semantic(device))
        for capability in (template.capabilities if template else ()):
            definition = capability.properties.get("process_definition")
            if isinstance(definition, dict):
                return definition
    except (ImportError, AttributeError):
        pass
    return {}


def _water_level(states: dict[str, Any]) -> float:
    if "water_level" in states:
        try:
            return max(0.0, float(states.get("water_level") or 0.0))
        except (TypeError, ValueError):
            return 0.0
    return 100.0 if bool(states.get("has_water", False)) else 0.0


def _children_semantics(state: dict[str, Any], parent_id: str) -> list[tuple[str, str]]:
    return [(child_id, semantic(node(state, child_id))) for child_id in children_of(state, parent_id)]


def start_process(state: dict[str, Any], device_id: str) -> bool:
    device = node(state, device_id)
    device_semantic = semantic(device)
    if any(str(p.get("device_id")) == str(device_id) for p in state.get("processes", [])):
        return False
    states = mutable_states(device)
    spec = process_definition(device)
    if spec:
        if spec.get("requires_water") and _water_level(states) < PROCESS_WATER_COST:
            return False
        for resource_key, cost in (spec.get("resource_costs") or {}).items():
            if float(states.get(resource_key, 0) or 0) < float(cost):
                return False
        child_pairs = _children_semantics(state, device_id)
        available = [sem for _, sem in child_pairs]
        if not all(required in available for required in spec["inputs"]):
            return False
        if spec.get("requires_water"):
            remaining_water = max(0.0, _water_level(states) - PROCESS_WATER_COST)
            states["water_level"] = remaining_water
            states["has_water"] = remaining_water > 0.0
        for resource_key, cost in (spec.get("resource_costs") or {}).items():
            remaining = max(0.0, float(states.get(resource_key, 0) or 0) - float(cost))
            states[resource_key] = int(remaining) if remaining.is_integer() else round(remaining, 4)
        output = spec["output"]
        duration = int(spec["duration"])
    else:
        return False
    states["is_on"] = True
    states["is_running"] = True
    states["cycle_remaining"] = duration
    process = {
        "device_id": str(device_id),
        "remaining": duration,
        "output": output,
        "recipe": str(spec.get("recipe") or device_semantic),
        "started_step": int(state.setdefault("world_state", {}).get("step", 0) or 0),
    }
    state.setdefault("processes", []).append(process)
    state.setdefault("world_state", {}).setdefault("event_log", []).append({
        "type": "process_started",
        "device_id": str(device_id),
        "output": output,
        "recipe": str(spec.get("recipe") or device_semantic),
        "duration": duration,
        "input_ids": [child_id for child_id, child_sem in _children_semantics(state, device_id) if child_sem in spec.get("inputs", ())],
    })
    return True


def process_ready(state: dict[str, Any], device_id: str) -> bool:
    device = node(state, device_id)
    spec = process_definition(device)
    if spec:
        if spec.get("requires_water") and _water_level(device.get("states") or {}) < PROCESS_WATER_COST:
            return False
        states = device.get("states") or {}
        if any(float(states.get(key, 0) or 0) < float(cost) for key, cost in (spec.get("resource_costs") or {}).items()):
            return False
        available = [sem for _, sem in _children_semantics(state, device_id)]
        return all(required in available for required in spec["inputs"])
    return True


def advance_processes(state: dict[str, Any]) -> list[str]:
    completed: list[str] = []
    remaining_processes = []
    for process in state.get("processes", []):
        device_id = str(process.get("device_id") or "")
        device = node(state, device_id)
        if not device:
            continue
        left = max(0, int(process.get("remaining") or 0) - 1)
        process["remaining"] = left
        mutable_states(device)["cycle_remaining"] = left
        if left > 0:
            remaining_processes.append(process)
            continue
        device_states = mutable_states(device)
        device_states["is_on"] = False
        device_states["is_running"] = False
        output_type = str(process.get("output") or "receipt")
        spec = process_definition(device)
        preserve = set(spec.get("preserve", ()))
        for child_id, child_semantic in _children_semantics(state, device_id):
            if child_semantic in spec.get("inputs", ()) and child_semantic not in preserve:
                state.setdefault("world_state", {}).setdefault("event_log", []).append({
                    "type": "process_consumed",
                    "device_id": device_id,
                    "item_id": child_id,
                    "semantic_type": child_semantic,
                })
                state.get("nodes", {}).pop(child_id, None)
                state.get("parent_of", {}).pop(child_id, None)
                state.get("relation_of", {}).pop(child_id, None)
        output_parent = device_id
        output_relation = "on"
        if output_type == "coffee":
            output_parent = next((child_id for child_id, sem in _children_semantics(state, device_id) if sem == "cup"), device_id)
            output_relation = "in"
        output_id = f"{output_type}_{int(state.setdefault('world_state', {}).get('step', 0))}_{len(state.get('nodes', {}))}"
        output = build_object_node(output_id, output_type)
        output["produced_by_device"] = device_id
        output["produced_by_recipe"] = str(process.get("recipe") or semantic(device))
        output["produced_at_step"] = int(state.setdefault("world_state", {}).get("step", 0) or 0)
        output["output_relation"] = output_relation
        output_states = output.setdefault("states", {})
        output_states.update(dict(spec.get("output_states") or {}))
        state.setdefault("nodes", {})[output_id] = output
        move_position(state, output_id, output_parent, output_relation)
        state.setdefault("world_state", {}).setdefault("event_log", []).append({
            "type": "process_completed",
            "device_id": device_id,
            "output_id": output_id,
            "output": output_type,
            "recipe": str(process.get("recipe") or semantic(device)),
            "produced_at_step": output["produced_at_step"],
        })
        completed.append(device_id)
    # Keep the world-state list identity intact; SceneGraph exposes it as the
    # rule-state process registry and replacing it would leave a stale alias.
    processes = state.setdefault("processes", [])
    processes[:] = remaining_processes
    return completed


def _template_property(item: dict[str, Any], property_name: str, default: Any = None) -> Any:
    value = item.get(property_name)
    if value is not None:
        return value
    try:
        from backend.generation.assets.object_library import OBJECT_LIBRARY
        template = OBJECT_LIBRARY.get(semantic(item))
        return template._property(property_name, default) if template else default
    except (ImportError, AttributeError):
        return default


def apply_timed_transitions(state: dict[str, Any], step: int = 0) -> list[str]:
    completed: list[str] = []
    parent_map = state.get("parent_of", {})
    world = state.setdefault("world_state", {})
    world.setdefault("temperature", "comfortable")
    world.setdefault("weather", "sunny")
    world.setdefault("day_phase", "day")
    world.setdefault("natural_dirt_enabled", True)
    _advance_environment(world, step)
    _apply_active_environment_controls(state)
    _advance_water_flows(state)
    _advance_released_objects(state)
    _advance_natural_changes(state, step)
    _advance_contained_profiles(state)
    elevator_events = advance_elevators(state, elapsed_steps=1)
    completed.extend(str(event.get("elevator_id")) for event in elevator_events if event.get("type") == "elevator_arrived")
    # Publish the transport-relative pose of every passenger as a normal node
    # update. The renderer owns a separate character body, so moving only the
    # car visual would otherwise leave an agent behind on the departure floor.
    graph = state.get("_graph")
    if graph is not None:
        for child_id, parent_id in list((state.get("parent_of") or {}).items()):
            parent = state.get("nodes", {}).get(parent_id) or {}
            relation = str((state.get("relation_of") or {}).get(child_id) or "").lower()
            if relation not in {"in", "inside"} or "transport_device" not in {str(value).lower() for value in (parent.get("capabilities") or ())}:
                continue
            child = state.get("nodes", {}).get(child_id)
            if not isinstance(child, dict):
                continue
            world_transform = graph._world_transform_for(child)
            child["world_transform"] = world_transform
            agent_state = (state.get("world_state", {}).get("agents") or {}).get(child_id)
            if isinstance(agent_state, dict):
                protocol_position = world_transform.get("position") or [0.0, 0.0, 0.0]
                agent_state["position"] = {
                    "x": float(protocol_position[0]),
                    "y": float(protocol_position[2]),
                    "z": -float(protocol_position[1]),
                }
                # room_id is the player's actual spatial room, not the
                # elevator's served floor label. While the passenger remains
                # inside the car, resolve through the canonical parent chain
                # to the shaft room; the floor label belongs only to the
                # elevator state machine.
                agent_state["room_id"] = str(
                    graph.room_of.get(child_id)
                    or graph.room_for(child_id)
                    or agent_state.get("room_id")
                    or ""
                )
    completed.extend(advance_processes(state))
    for node_id, item in state.get("nodes", {}).items():
        item_semantic = semantic(item)
        item_states = mutable_states(item)
        if bool(item_states.get(DiscreteState.IS_PRESSED.value, False)):
            item_states[DiscreteState.IS_PRESSED.value] = False
        configured_duration = profile_duration(item)
        process_duration = int(process_definition(item).get("duration") or 0)
        if "transport_device" in object_capabilities(item):
            # Elevator scheduling and door phases are handled by the generic
            # elevator rule above; do not run the legacy fixed-cycle branch.
            continue
        if not configured_duration and not process_duration:
            continue
        if not bool(item_states.get(DiscreteState.IS_RUNNING.value, item_states.get(DiscreteState.IS_ON.value, False))):
            continue
        item_states[DiscreteState.IS_RUNNING.value] = True
        remaining = int(item_states.get(DiscreteState.CYCLE_REMAINING.value) or configured_duration or process_duration or 2)
        remaining = max(0, remaining - 1)
        item_states[DiscreteState.CYCLE_REMAINING.value] = remaining
        if remaining > 0:
            continue
        item_states[DiscreteState.IS_ON.value] = False
        item_states[DiscreteState.IS_RUNNING.value] = False
        if "transport_device" in object_capabilities(item):
            destination = str(item.get("requested_room") or "")
            served = {str(room_id) for room_id in item.get("served_rooms") or item.get("transport_rooms") or []}
            if destination and destination in served and destination in state.get("nodes", {}):
                for child_id, child_parent in list(parent_map.items()):
                    if child_parent != node_id:
                        continue
                    # Riders and carried objects remain structurally inside
                    # the moving car. Only their semantic room projection
                    # changes to the served landing; replacing the `in`
                    # edge would detach them from the cabin and make them
                    # stop following its transform.
                    state.setdefault("room_of", {})[child_id] = destination
                item["current_room"] = destination
            item.pop("requested_room", None)
            item_states[DiscreteState.IS_OPEN.value] = True
            state.setdefault("world_state", {}).setdefault("event_log", []).append({
                "type": "elevator_arrived",
                "elevator_id": str(node_id),
                "destination_room": destination,
            })
            completed.append(node_id)
            continue
        for child_id in descendants_of(state, node_id):
            child = node(state, child_id)
            child_capabilities = object_capabilities(child)
            profile = item.get("temporal_profile") or {}
            if not profile:
                try:
                    from backend.generation.assets.object_library import OBJECT_LIBRARY
                    template = OBJECT_LIBRARY.get(item_semantic)
                    if template:
                        profile = template._property("temporal_profile", {})
                except (ImportError, AttributeError):
                    profile = {}
            apply_effects(child, child_capabilities, temporal_effects({"temporal_profile": profile}, "complete"))
        completed.append(node_id)
    return completed


def _advance_contained_profiles(state: dict[str, Any]) -> None:
    """Advance effects declared by a support/container capability.

    This handles drying racks and future passive processing surfaces without
    naming a concrete object. A contained item may expose several independent
    state transitions; the profile controls only the states it declares.
    """
    for parent_id, parent in state.get("nodes", {}).items():
        profile = contained_profile(parent)
        duration = profile_duration(parent, contained=True)
        if not profile or duration <= 0:
            continue
        effects = temporal_effects({"temporal_profile": profile}, "complete")
        if not effects:
            continue
        for child_id in descendants_of(state, str(parent_id)):
            child = node(state, child_id)
            child_states = mutable_states(child)
            capabilities = object_capabilities(child)
            matching = tuple(effect for effect in effects if not effect.capability or effect.capability in capabilities)
            if not matching:
                continue
            if "cycle_remaining" not in child_states or int(child_states.get("cycle_remaining") or 0) <= 0:
                # Only start the process when the declared input state is
                # present; dryable objects, for example, must be wet first.
                if any(effect.state == DiscreteState.IS_WET.value for effect in matching) and not child_states.get(DiscreteState.IS_WET.value, False):
                    continue
                room_id = str(state.get("room_of", {}).get(str(parent_id)) or "")
                child_states[DiscreteState.CYCLE_REMAINING.value] = contextual_duration(
                    profile, default=duration, world=state.setdefault("world_state", {}), room_id=room_id,
                )
            remaining = max(0, int(child_states.get(DiscreteState.CYCLE_REMAINING.value) or 0) - 1)
            child_states[DiscreteState.CYCLE_REMAINING.value] = remaining
            if remaining:
                continue
            apply_effects(child, capabilities, matching)
            state.setdefault("world_state", {}).setdefault("event_log", []).append({
                "type": str(profile.get("event_type") or "contained_process_completed"),
                "support_id": str(parent_id),
                "item_id": str(child_id),
            })


def _advance_water_flows(state: dict[str, Any]) -> None:
    """Advance reservoirs using their declared fill/drain rates."""
    for sink in state.get("nodes", {}).values():
        if "water_reservoir" not in object_capabilities(sink):
            continue
        sink_states = mutable_states(sink)
        current = float(sink_states.get("water_level") or (100.0 if sink_states.get("has_water") else 0.0))
        sink_id = str(sink.get("id") or "")
        controlled = any(
            str(edge.get("target_id") or "") == sink_id
            and str(edge.get("relation") or "") == "controls"
            and bool(mutable_states(node(state, str(edge.get("source_id") or ""))).get("is_on", False))
            for edge in state.get("control_edges", [])
        )
        flowing = bool(sink_states.get("water_flowing", False)) or controlled
        sink_states["water_flowing"] = flowing
        if flowing:
            delta = float(object_property(sink, "fill_rate_per_step", 20.0) or 20.0)
            next_level = min(100.0, current + delta)
        else:
            delta = float(object_property(sink, "drain_rate_per_step", 60.0) or 60.0)
            next_level = max(0.0, current - delta)
        if next_level != current:
            sink_states["water_level"] = round(next_level, 2)
            sink_states["has_water"] = next_level > 0.0


def advance_time(world: dict[str, Any], elapsed_steps: int = 1) -> list[str]:
    """Advance one shared simulation clock and apply state transitions.

    ``world`` is the rule-state mapping used by ``SceneGraph``. Every elapsed
    step runs the same transition pipeline, so players, NPCs, and scripted
    events share one clock. The function owns the step counter; callers should
    not increment ``world_state.step`` separately.
    """
    steps = max(0, int(elapsed_steps))
    completed: list[str] = []
    state_world = world.setdefault("world_state", {})
    for _ in range(steps):
        current_step = int(state_world.get("step") or 0)
        completed.extend(apply_timed_transitions(world, current_step))
        state_world["step"] = current_step + 1
    return completed


def _advance_environment(world: dict[str, Any], step: int) -> None:
    """Keep environment deliberately discrete for the frozen baseline."""
    # ``step`` is the current tick, not an elapsed duration.  Advance the
    # clock by one configured quantum per call; multiplying by ``step`` would
    # make time grow quadratically across an episode.
    minute = int(world.get("time_min") or 0) + int(world.get("minutes_per_step") or 10)
    world["time_min"] = minute % (24 * 60)
    world["day"] = int(world.get("day") or 1) + (1 if minute >= 24 * 60 else 0)
    world["day_phase"] = "night" if (minute % 1440) < 360 or (minute % 1440) >= 1320 else "day"
    world.setdefault("room_temperature", {})
    world.setdefault("room_humidity", {})
    baseline = {"comfortable": "room"}.get(str(world.get("temperature") or "comfortable"), str(world.get("temperature") or "room"))
    for room_id in list(world["room_temperature"]):
        current = str(world["room_temperature"].get(room_id) or baseline)
        if current == baseline:
            continue
        world["room_temperature"][room_id] = _step_toward(current, baseline)


def _step_toward(current: str, target: str) -> str:
    order = ("cold", "room", "hot")
    if current not in order or target not in order:
        return target
    index = order.index(current)
    target_index = order.index(target)
    return order[index + (1 if target_index > index else -1)] if index != target_index else current


def _apply_active_environment_controls(state: dict[str, Any]) -> None:
    world = state.setdefault("world_state", {})
    room_temperatures = world.setdefault("room_temperature", {})
    for node_id, item in state.get("nodes", {}).items():
        effect = object_property(item, "environment_effect", {}) or {}
        if not isinstance(effect, dict) or not effect.get("channel"):
            continue
        if not bool(mutable_states(item).get("is_on", False)):
            continue
        room_id = str(state.get("room_of", {}).get(node_id) or "")
        if not room_id:
            continue
        channel = str(effect["channel"])
        value = effect.get("active_value")
        world.setdefault(f"room_{channel}", {})[room_id] = value


def _advance_released_objects(state: dict[str, Any]) -> None:
    """Advance released objects through a discrete gravity/floor contact model."""
    world = state.setdefault("world_state", {})
    step_cm = max(1.0, float(world.get("gravity_step_cm") or 50.0))
    for node_id, item in state.get("nodes", {}).items():
        if item.get("physics_state") != "falling":
            continue
        height = max(0.0, float(item.get("drop_height_cm") or 0.0) - step_cm)
        item["drop_height_cm"] = height
        if height > 0:
            continue
        item["physics_state"] = "settled"
        world.setdefault("event_log", []).append({
            "type": "object_settled",
            "object_id": str(node_id),
            "item_id": str(node_id),
            "room_id": str(item.get("release_room") or ""),
        })


def _advance_natural_changes(state: dict[str, Any], step: int) -> None:
    world = state.setdefault("world_state", {})
    counters = world.setdefault("natural_change_counters", {})
    parents = state.get("parent_of", {})
    for node_id, item in state.get("nodes", {}).items():
        semantic_type = semantic(item)
        states = mutable_states(item)
        capabilities = object_capabilities(item)
        if "water_container" in capabilities and (
            bool(states.get("has_water")) or float(states.get("water_level", 0.0) or 0.0) > 0.0
        ):
            plant_ids = [child_id for child_id, parent_id in parents.items() if parent_id == node_id and "plant_life" in object_capabilities(node(state, child_id))]
            if plant_ids:
                age = int(counters.get(node_id, 0)) + 1
                counters[node_id] = age
                decay = _template_property(item, "water_decay", {}) or {}
                interval = max(1, int(decay.get("interval_steps") or 12))
                if age >= interval:
                    if "water_level" in states:
                        delta = float(decay.get("delta") or 20.0)
                        states["water_level"] = max(0.0, round(float(states.get("water_level") or 0.0) - delta, 2))
                        states["has_water"] = states["water_level"] > 0.0
                    else:
                        states["has_water"] = False
                    counters[node_id] = 0
                    if not states.get("has_water", False):
                        world.setdefault("event_log", []).append({
                            "type": "water_depleted",
                            "container_id": str(node_id),
                        })
                        for plant_id in plant_ids:
                            plant_states = mutable_states(node(state, plant_id))
                            was_wilted = bool(plant_states.get("is_wilted", False))
                            plant_states["vitality"] = max(0.0, round(float(plant_states.get("vitality", 1.0)) - 0.2, 2))
                            plant_states["is_wilted"] = plant_states["vitality"] <= 0.0
                            if plant_states["is_wilted"] and not was_wilted:
                                world.setdefault("event_log", []).append({
                                    "type": "flower_wilted",
                                    "flower_id": str(plant_id),
                                    "vase_id": str(node_id),
                                })
        elif "perishable" in capabilities and states.get("is_rotten") is False:
            age = int(counters.get(node_id, 0)) + 1
            counters[node_id] = age
            profile = _template_property(item, "natural_profile", {}) or {}
            interval = max(1, int(profile.get("interval_steps") or 144))
            # Freshness is continuous, while spoiled/rotten are compatibility
            # projections for planners and UI filters.
            freshness = float(states.get("freshness", 100.0) or 0.0)
            decay = float(profile.get("freshness_decay") or (100.0 / interval))
            states["freshness"] = max(0.0, round(freshness - decay, 4))
            if age >= interval or states["freshness"] <= float(profile.get("rotten_at") or 0.0):
                states["freshness"] = 0.0
                states["is_rotten"] = True
                world.setdefault("event_log", []).append({
                    "type": "food_spoiled",
                    "item_id": str(node_id),
                    "semantic_type": semantic_type,
                })
            elif states["freshness"] <= float(profile.get("spoiled_below") or 50.0):
                states["is_spoiled"] = True
        elif states.get("is_dirty") is False and "cleanable" in object_capabilities(item):
            # Dirt accumulation is deliberately slow and opt-out via a world
            # flag, so short planning episodes remain stable by default.
            if world.get("natural_dirt_enabled", False):
                age = int(counters.get(node_id, 0)) + 1
                counters[node_id] = age
                dirt_steps = max(1, int(world.get("natural_dirt_steps") or 60))
                if age >= dirt_steps:
                    states["is_dirty"] = True
                    counters[node_id] = 0
                    world.setdefault("event_log", []).append({
                        "type": "dirt_accumulated",
                        "item_id": str(node_id),
                    })

        # Thermal relaxation is represented with the existing discrete
        # temperature enum.  Objects drift one level toward their room's
        # temperature on each tick unless a process explicitly owns them.
        object_temperature = states.get("temperature")
        if object_temperature in {"cold", "warm", "hot"}:
            room_id = state.get("room_of", {}).get(node_id, "")
            room_temperature = (world.get("room_temperature") or {}).get(room_id)
            target_temperature = str(room_temperature or world.get("temperature") or "comfortable")
            target_temperature = {"comfortable": "room"}.get(target_temperature, target_temperature)
            if target_temperature in {"cold", "room", "warm", "hot"}:
                next_temperature = _step_thermal_toward(str(object_temperature), target_temperature)
                if next_temperature != object_temperature:
                    states["temperature"] = next_temperature
                    world.setdefault("event_log", []).append({
                        "type": "temperature_relaxed",
                        "item_id": str(node_id),
                        "from": str(object_temperature),
                        "to": next_temperature,
                    })


def _step_thermal_toward(current: str, target: str) -> str:
    order = ("cold", "room", "warm", "hot")
    if current not in order or target not in order:
        return target
    current_index, target_index = order.index(current), order.index(target)
    if current_index == target_index:
        return current
    return order[current_index + (1 if target_index > current_index else -1)]


__all__ = [
    "RECIPE_SPECS",
    "advance_processes",
    "advance_time",
    "apply_timed_transitions",
    "process_definition",
    "process_ready",
    "start_process",
]
