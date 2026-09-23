from __future__ import annotations

from typing import Any

from .domain_rules import APPLIANCE_CYCLE_STEPS, CLOTH_SEMANTICS, DRYING_RACK_STEPS
from .predicates import mutable_states, node, parent_of, semantic
from .states import DiscreteState
from .processes import advance_processes


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
    _advance_released_objects(state)
    _advance_natural_changes(state, step)
    completed.extend(advance_processes(state))
    for node_id, item in state.get("nodes", {}).items():
        item_semantic = semantic(item)
        item_states = mutable_states(item)
        if bool(item_states.get(DiscreteState.IS_PRESSED.value, False)):
            item_states[DiscreteState.IS_PRESSED.value] = False
        parent = node(state, str(parent_map.get(node_id) or ""))
        if semantic(parent) == "drying_rack" and bool(item_states.get(DiscreteState.IS_WET.value, False)):
            rack_room = str(state.get("room_of", {}).get(str(parent_map.get(node_id) or "")) or "")
            remaining = int(item_states.get(DiscreteState.CYCLE_REMAINING.value) or _drying_steps(world, rack_room))
            remaining = max(0, remaining - 1)
            item_states[DiscreteState.CYCLE_REMAINING.value] = remaining
            if remaining == 0:
                item_states[DiscreteState.IS_WET.value] = False
                state.setdefault("world_state", {}).setdefault("event_log", []).append({
                    "type": "drying_completed",
                    "item_id": str(node_id),
                    "rack_id": str(parent_map.get(node_id) or ""),
                })
                completed.append(node_id)
        if item_semantic not in APPLIANCE_CYCLE_STEPS or item_semantic in {"coffeemachine", "coffee_machine", "workbench"}:
            continue
        if not bool(item_states.get(DiscreteState.IS_RUNNING.value, item_states.get(DiscreteState.IS_ON.value, False))):
            continue
        item_states[DiscreteState.IS_RUNNING.value] = True
        remaining = int(item_states.get(DiscreteState.CYCLE_REMAINING.value) or APPLIANCE_CYCLE_STEPS[item_semantic])
        remaining = max(0, remaining - 1)
        item_states[DiscreteState.CYCLE_REMAINING.value] = remaining
        if remaining > 0:
            continue
        item_states[DiscreteState.IS_ON.value] = False
        item_states[DiscreteState.IS_RUNNING.value] = False
        if item_semantic == "elevator":
            destination = str(item.get("requested_room") or "")
            served = {str(room_id) for room_id in item.get("served_rooms") or item.get("transport_rooms") or []}
            if destination and destination in served and destination in state.get("nodes", {}):
                for child_id, child_parent in list(parent_map.items()):
                    if child_parent != node_id:
                        continue
                    child = node(state, child_id)
                    child["parent"] = destination
                    child["runtime_relation"] = "at"
                    parent_map[child_id] = destination
                    state.setdefault("relation_of", {})[child_id] = "at"
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
        for child_id, child_parent in parent_map.items():
            if child_parent != node_id:
                continue
            child = node(state, child_id)
            child_states = mutable_states(child)
            child_semantic = semantic(child)
            if item_semantic in {"washer", "washing_machine"} and child_semantic in CLOTH_SEMANTICS:
                child_states[DiscreteState.IS_DIRTY.value] = False
                child_states[DiscreteState.IS_WET.value] = True
                child_states[DiscreteState.FOLDED.value] = False
                child_states[DiscreteState.CYCLE_REMAINING.value] = DRYING_RACK_STEPS
            if item_semantic in {"dryer", "clothesdryer"} and child_semantic in CLOTH_SEMANTICS:
                child_states[DiscreteState.IS_WET.value] = False
                child_states[DiscreteState.FOLDED.value] = False
            if item_semantic == "dishwasher" and child_semantic in {"bowl", "plate", "cup", "dish", "utensil"}:
                child_states[DiscreteState.IS_DIRTY.value] = False
                if DiscreteState.IS_WET.value in child_states:
                    child_states[DiscreteState.IS_WET.value] = False
            if item_semantic == "microwave" and child_semantic in {"milk", "juice", "food", "drink", "water"}:
                child_states[DiscreteState.TEMPERATURE.value] = "hot"
        completed.append(node_id)
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
        if semantic(item) not in {"air_conditioner", "air_conditioning", "aircon", "fan", "ceiling_fan", "ventilator"}:
            continue
        if not bool(mutable_states(item).get("is_on", False)):
            continue
        room_id = str(state.get("room_of", {}).get(node_id) or "")
        if room_id and semantic(item) in {"air_conditioner", "air_conditioning", "aircon"}:
            room_temperatures[room_id] = "cold"
        elif room_id:
            world.setdefault("room_ventilation", {})[room_id] = "active"


def _drying_steps(world: dict[str, Any], room_id: str = "") -> int:
    weather = str(world.get("weather") or "sunny").lower()
    steps = {"sunny": 6, "cloudy": 8, "rainy": 12}.get(weather, DRYING_RACK_STEPS)
    humidity_map = world.get("room_humidity") or {}
    try:
        humidity = float(humidity_map.get(room_id, world.get("humidity", 50.0)))
    except (TypeError, ValueError):
        humidity = 50.0
    if humidity >= 80:
        steps += 4
    elif humidity <= 30:
        steps = max(1, steps - 2)
    return steps


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
        if semantic_type == "vase" and (
            bool(states.get("has_water")) or float(states.get("water_level", 0.0) or 0.0) > 0.0
        ):
            plant_ids = [child_id for child_id, parent_id in parents.items() if parent_id == node_id and semantic(node(state, child_id)) in {"plant", "flower"}]
            if plant_ids:
                age = int(counters.get(node_id, 0)) + 1
                counters[node_id] = age
                if age >= 12:
                    if "water_level" in states:
                        states["water_level"] = max(0.0, round(float(states.get("water_level") or 0.0) - 20.0, 2))
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
        elif semantic_type in {"food", "fruit", "vegetable", "milk", "juice"} and states.get("is_rotten") is False:
            age = int(counters.get(node_id, 0)) + 1
            counters[node_id] = age
            if age >= 144:
                states["is_rotten"] = True
                world.setdefault("event_log", []).append({
                    "type": "food_spoiled",
                    "item_id": str(node_id),
                    "semantic_type": semantic_type,
                })
        elif states.get("is_dirty") is False and semantic_type in {
            "plate", "cup", "mug", "bowl", "table", "counter", "desk", "floor", "sink", "toilet",
        }:
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


__all__ = ["apply_timed_transitions"]
