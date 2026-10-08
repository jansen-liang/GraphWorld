"""Canonical graph store with Edge-owned relationships."""

from __future__ import annotations

import copy
import math
import logging
from typing import Any, Iterable
from uuid import uuid4

from backend.adapter.animation.cues import visual_cues
from ...core.edge import Edge, POSITION_RELATIONS, ROOM_CONNECTIVITY_RELATIONS, move_position_in_state
from ...core.node import Node
from ...core.transform import IDENTITY_TRANSFORM, Transform
from backend.runtime.scene_schema import validate_canonical_scene
from ...core.state import DISCRETE_STATE_SPACE
from backend.runtime.transitions import transition_log

logger = logging.getLogger(__name__)


# These fields are transport-process state carried alongside the canonical
# discrete states. They are intentionally scoped to transport devices; they
# are not a general escape hatch for arbitrary node state.
TRANSPORT_RUNTIME_STATE_SPACE = frozenset({
    "arrival_pending", "current_height", "motion_state", "target_height",
    "dwell_remaining",
})


def _layout_rotation_quaternion(placement: dict[str, Any]) -> list[float]:
    """Convert authored Three.js-style quarter-turn Euler angles to protocol.

    Layout rotations use the editor's XYZ Euler convention. The protocol is
    Z-up, while Three.js is Y-up, so conjugate the editor quaternion by the
    same X-axis basis change used by ``applyProtocolToThree``.
    """
    def quarter_angle(*names: str) -> float:
        for name in names:
            if placement.get(name) is not None:
                return float(placement.get(name) or 0.0) * math.pi / 2.0
        return 0.0

    x, y, z = (quarter_angle("rotation_x"), quarter_angle("rotation_y", "rotation"), quarter_angle("rotation_z"))
    sx, cx = math.sin(x / 2.0), math.cos(x / 2.0)
    sy, cy = math.sin(y / 2.0), math.cos(y / 2.0)
    sz, cz = math.sin(z / 2.0), math.cos(z / 2.0)
    # THREE.Euler order XYZ.
    q_three = [
        sx * cy * cz + cx * sy * sz,
        cx * sy * cz - sx * cy * sz,
        cx * cy * sz + sx * sy * cz,
        cx * cy * cz - sx * sy * sz,
    ]

    def mul(a: list[float], b: list[float]) -> list[float]:
        ax, ay, az, aw = a
        bx, by, bz, bw = b
        return [
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz,
        ]

    basis = [math.sin(math.pi / 4.0), 0.0, 0.0, math.cos(math.pi / 4.0)]
    inverse_basis = [-basis[0], -basis[1], -basis[2], basis[3]]
    return mul(mul(inverse_basis, q_three), basis)


class _RuntimeIndex(dict[str, Any]):
    """One runtime-owned map with stable editor identifiers as lookup keys."""

    def __init__(self, *args: Any, aliases: dict[str, str] | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.aliases = aliases or {}

    def _key(self, key: object) -> object:
        return self.aliases.get(str(key), key)

    def __contains__(self, key: object) -> bool:
        return super().__contains__(self._key(key))

    def __getitem__(self, key: object) -> Any:
        return super().__getitem__(self._key(key))

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(self._key(key), value)

    def __delitem__(self, key: object) -> None:
        super().__delitem__(self._key(key))

    def get(self, key: object, default: Any = None) -> Any:
        return super().get(self._key(key), default)

    def pop(self, key: object, *args: Any) -> Any:
        return super().pop(self._key(key), *args)


def _values(scene: dict[str, Any], plural: str, singular: str) -> list[dict[str, Any]]:
    if isinstance(scene.get(plural), list):
        return copy.deepcopy(scene.get(plural) or [])
    if isinstance(scene.get(singular), dict):
        return copy.deepcopy(list((scene.get(singular) or {}).values()))
    return []


move_position = move_position_in_state


class World:
    """One mutable world graph; relationship indices are disposable caches."""

    def __init__(self, scene: dict[str, Any], *, run_id: str | None = None):
        self.run_id = str(run_id or f"sim_{uuid4().hex}")
        scene = validate_canonical_scene(scene)
        self.scene_name = str(scene.get("scene_name") or "scene")
        core_keys = {"scene_name", "nodes", "node", "edges", "edge", "world_state", "processes"}
        self.metadata = copy.deepcopy({key: value for key, value in scene.items() if key not in core_keys})
        raw_nodes = _values(scene, "nodes", "node")
        self.runtime_id_by_editor_id: dict[str, str] = {}
        self.editor_id_by_runtime_id: dict[str, str] = {}
        self.nodes: _RuntimeIndex = _RuntimeIndex()
        for raw in raw_nodes:
            model = Node.from_dict(raw)
            editor_id = model.editor_id or model.id
            if not editor_id:
                continue
            runtime_id = f"{self.run_id}:{editor_id}"
            model.id = editor_id
            model.editor_id = editor_id
            model.runtime_id = runtime_id
            record = model.to_dict()
            record["id"] = editor_id
            self.runtime_id_by_editor_id[editor_id] = runtime_id
            self.editor_id_by_runtime_id[runtime_id] = editor_id
            self.nodes[editor_id] = record
        self.nodes.aliases = {}
        self.edges = [
            self._runtime_edge(model.to_dict())
            for raw in _values(scene, "edges", "edge")
            if (model := Edge.from_dict(raw)).source_id and model.target_id and model.relation
        ]
        self._hydrate_layout_geometry(scene)
        self._reconcile_layout_relationships(scene)
        self.world_state = copy.deepcopy(scene.get("world_state") or {})
        self._initialize_world_state()
        self._validate_node_states()
        self.refresh_indices()

    def resolve_id(self, value: str) -> str:
        value = str(value or "")
        if value in self.nodes:
            return value
        return self.editor_id_by_runtime_id.get(value, value)

    def _hydrate_layout_geometry(self, scene: dict[str, Any]) -> None:
        """Expose authored dimensions/transforms to generic runtime solvers.

        Compact scene nodes intentionally omit renderer-only geometry. Runtime
        placement still needs the same asset footprint and root transform, so
        copy these derived values once from the canonical layout rather than
        making every action know about layout dictionaries.
        """
        layout = scene.get("layout") if isinstance(scene.get("layout"), dict) else {}
        placements = layout.get("objects") if isinstance(layout, dict) else {}
        if not isinstance(placements, dict):
            return
        for node_id, placement in placements.items():
            node = self.nodes.get(str(node_id))
            if not node or not isinstance(placement, dict):
                continue
            width = float(placement.get("width_cm") or 0.0)
            depth = float(placement.get("depth_cm") or 0.0)
            height = float(placement.get("height_cm") or 0.0)
            if width > 0 and depth > 0 and height > 0:
                node.setdefault("dimensions_cm", [width, depth, height])
                node.setdefault("bounds_cm", [width, depth, height])
                # A support-capable root always has a concrete top surface.
                # Older scene exports declared only can_support/place_target;
                # complete that contract once at the runtime boundary from
                # the authored asset dimensions.
                capabilities = {str(value).lower() for value in (node.get("capabilities") or ())}
                if (bool(node.get("can_support")) or "support_surface" in capabilities) and not isinstance(node.get("surface_spec"), dict):
                    node["surface_spec"] = {
                        "width_cm": width,
                        "depth_cm": depth,
                        "grid_size_cm": 1.0,
                    }
            if isinstance(node.get("world_transform"), dict):
                # The layout is the authored orientation source. A snapshot
                # can already contain a renderer-generated identity (or a
                # stale orientation from an older version), so preserving it
                # here makes Run disagree with the editor for rotated assets.
                # Keep the runtime position/scale, but always refresh yaw from
                # the current layout placement.
                if any(placement.get(name) is not None for name in ("rotation_x", "rotation_y", "rotation_z", "rotation")):
                    node["world_transform"]["rotation"] = _layout_rotation_quaternion(placement)
                continue
            room_id = str(placement.get("room_id") or "")
            room = (layout.get("rooms") or {}).get(room_id, {}) if isinstance(layout.get("rooms"), dict) else {}
            grid = float(layout.get("grid_size") or 0.1)
            if isinstance(room, dict) and width > 0 and depth > 0 and height > 0:
                # Layout object z_cm is local to its room. Runtime snapshots
                # must lift objects on upper storeys by the room's authored
                # floor elevation; otherwise editor mode shows F2/F3 hall
                # buttons correctly while Run projects them back onto F1.
                floor_number = float(room.get("floor_number") or 1.0)
                floor_pitch = float(layout.get("floor_height_m") or 3.2)
                floor_elevation = max(0.0, floor_number - 1.0) * floor_pitch
                # Layout rotation is expressed as quarter turns around the
                # vertical axis. Runtime snapshots must carry that authored
                # orientation so the run renderer does not reset rotated
                # fixtures (such as sinks) to the identity quaternion.
                node["world_transform"] = {
                    "position": [
                        (float(placement.get("x_cm") or 0.0) + width / 2.0) / 100.0,
                        -(float(placement.get("y_cm") or 0.0) + depth / 2.0) / 100.0,
                        floor_elevation + float(placement.get("z_cm") or 0.0) / 100.0 + height / 200.0,
                    ],
                    "rotation": _layout_rotation_quaternion(placement),
                    "scale": [1.0, 1.0, 1.0],
                }

    def _runtime_edge(self, edge: dict[str, Any]) -> dict[str, Any]:
        edge["source_id"] = self.resolve_id(edge["source_id"])
        edge["target_id"] = self.resolve_id(edge["target_id"])
        return edge

    def _reconcile_layout_relationships(self, scene: dict[str, Any]) -> None:
        """Keep persisted editor placement and runtime containment in sync.

        A surface/floor placement is not inside the previously used container,
        even when an old snapshot still contains that stale ``in`` edge.  The
        layout is authoritative for editor-authored placement; true contained
        placements retain their container edge and therefore its access rules.
        """
        layout = scene.get("layout")
        placements = layout.get("objects") if isinstance(layout, dict) else None
        if not isinstance(placements, dict):
            return
        node_ids = set(self.nodes)
        room_ids = {
            node_id for node_id, item in self.nodes.items()
            if str(item.get("node_type") or "").lower() == "room"
        }
        if not room_ids:
            return
        for object_id, placement in placements.items():
            object_id = str(object_id)
            if object_id not in node_ids or not isinstance(placement, dict):
                continue
            # Runtime interaction state has precedence over the editor's
            # original layout.  In particular, a picked object keeps its
            # held_by edge across the next session dispatch; otherwise the
            # layout reconciliation would immediately drop it back on the
            # floor before the renderer can attach it to the hand.
            current_position = next(
                (
                    edge for edge in self.edges
                    if str(edge.get("target_id") or "") == object_id
                    and str(edge.get("relation") or "").lower() in POSITION_RELATIONS
                ),
                None,
            )
            if current_position and bool((current_position.get("properties") or {}).get("canonical")):
                # A serialized runtime snapshot carries the authoritative
                # positional edge. Do not replace it with stale editor layout
                # coordinates when the next World instance is reconstructed.
                continue
            if current_position and str(current_position.get("relation") or "").lower().startswith("held_by"):
                continue
            mode = str(placement.get("placement_mode") or "surface").lower()
            if mode in {"contained", "wall_mounted"}:
                continue
            room_id = str(placement.get("room_id") or "")
            if room_id not in room_ids:
                continue
            # World construction is the editor-source boundary. If the source
            # layout says an object is a surface/floor object, a stale legacy
            # containment edge must not survive and make the runtime enforce a
            # closed-container precondition for an object visibly on the floor.
            # Runtime actions mutate this same World afterwards, so this
            # reconciliation does not overwrite a live action's edge.
            self.edges[:] = [
                edge for edge in self.edges
                if not (
                    str(edge.get("target_id") or "") == object_id
                    and str(edge.get("relation") or "").lower() in POSITION_RELATIONS
                )
            ]
            self.edges.append(Edge(
                room_id,
                object_id,
                "inside_room",
                {"canonical": True, "layout_reconciled": True},
                category="structural",
            ).to_dict())

    def _initialize_world_state(self) -> None:
        defaults = {
            "step": 0,
            "event_log": [],
            "blocking_cases": [],
            "temperature": "comfortable",
            "weather": "sunny",
            "day_phase": "day",
            "room_temperature": {},
            "room_humidity": {},
            "natural_change_counters": {},
            "natural_dirt_enabled": True,
            "processes": [],
        }
        for key, value in defaults.items():
            self.world_state.setdefault(key, copy.deepcopy(value))

    def ensure_agent_state(self, agent_id: str) -> dict[str, Any]:
        """Return the runtime-owned transform for an agent.

        Agent motion is runtime state, not editor layout.  A missing transform
        starts at the center of the agent's authored room.
        """
        agents = self.world_state.setdefault("agents", {})
        agent_id = self.resolve_id(agent_id)
        state = agents.setdefault(agent_id, {})
        if not isinstance(state.get("position"), dict):
            room_id = self.room_of.get(agent_id, "")
            layout = self.metadata.get("layout") or {}
            room = (layout.get("rooms") or {}).get(room_id, {}) if isinstance(layout, dict) else {}
            cell = float(layout.get("grid_size") or 0.5) if isinstance(layout, dict) else 0.5
            state["position"] = {
                "x": (float(room.get("grid_x") or 0) + float(room.get("width_cells") or 1) / 2) * cell,
                "y": 1.6,
                "z": (float(room.get("grid_y") or 0) + float(room.get("depth_cells") or 1) / 2) * cell,
            }
        state.setdefault("moving", False)
        state.setdefault("room_id", self.room_of.get(agent_id, ""))
        return state

    def move_agent(self, agent_id: str, dx: float, dz: float, elapsed_seconds: float) -> dict[str, Any]:
        """Advance an agent transform in the authoritative runtime."""
        state = self.ensure_agent_state(agent_id)
        previous_room_id = str(state.get("room_id") or self.room_of.get(agent_id, ""))
        position = state["position"]
        duration = max(0.0, min(float(elapsed_seconds), 1.0))
        speed = 2.2
        length = math.hypot(dx, dz)
        if length > 1e-9 and duration > 0:
            scale = speed * duration / max(1.0, length)
            position["x"] += float(dx) * scale
            position["z"] += float(dz) * scale
            state["moving"] = True
        else:
            state["moving"] = False
        # The browser sends horizontal movement deltas only. When a passenger
        # has just arrived in a moving car, its authoritative Y is updated by
        # the transport projection, but the next move request can still carry
        # the pre-transport local value. Re-anchor the player to the car's
        # current floor before classifying overlapping floor footprints; this
        # prevents an exit from being interpreted as a return to 1F.
        current_parent = self.parent_of.get(agent_id, "")
        parent_item = self.nodes.get(current_parent) or {}
        if "transport_device" in {str(value).lower() for value in (parent_item.get("capabilities") or ())}:
            transport_height = (parent_item.get("states") or {}).get("current_height")
            if transport_height is not None:
                try:
                    position["y"] = float(transport_height) + 1.6
                except (TypeError, ValueError):
                    pass
        layout = self.metadata.get("layout") or {}
        rooms = layout.get("rooms") if isinstance(layout, dict) else {}
        if isinstance(rooms, dict) and rooms:
            cell = float(layout.get("grid_size") or 0.5)
            max_x = max((float(room.get("grid_x") or 0) + float(room.get("width_cells") or 0)) * cell for room in rooms.values() if isinstance(room, dict))
            max_z = max((float(room.get("grid_y") or 0) + float(room.get("depth_cells") or 0)) * cell for room in rooms.values() if isinstance(room, dict))
            position["x"] = max(0.15, min(float(position["x"]), max_x - 0.15))
            position["z"] = max(0.15, min(float(position["z"]), max_z - 0.15))
        room_id = ""
        room_candidates: list[tuple[float, str]] = []
        if isinstance(rooms, dict):
            for candidate, room in rooms.items():
                if not isinstance(room, dict):
                    continue
                cell = float(layout.get("grid_size") or 0.5)
                min_x = float(room.get("grid_x") or 0) * cell
                min_z = float(room.get("grid_y") or 0) * cell
                if min_x <= position["x"] <= min_x + float(room.get("width_cells") or 0) * cell and min_z <= position["z"] <= min_z + float(room.get("depth_cells") or 0) * cell:
                    floor_number = float(room.get("floor_number") or 1)
                    floor_y = 0.0 if str(candidate).startswith("elevator_shaft") else max(0.0, floor_number - 1.0) * 3.2
                    room_height = 9.6 if str(candidate).startswith("elevator_shaft") else 3.2
                    # Several floors intentionally share the same 2D
                    # footprint. Select the room whose storey contains the
                    # player's vertical position instead of taking the first
                    # dictionary entry (which always selected 1F).
                    if floor_y - 0.25 <= float(position.get("y") or 0.0) <= floor_y + room_height + 0.25:
                        room_candidates.append((abs(float(position.get("y") or 0.0) - floor_y), str(candidate)))
            if room_candidates:
                room_id = min(room_candidates, key=lambda item: item[0])[1]
                # The client sends horizontal movement, so derive the
                # player's world height from the selected landing room before
                # testing whether the point is actually inside the car.
                # This keeps 2D-overlapping floors distinct without treating
                # every point in a landing as being inside the elevator.
                selected_room = rooms.get(room_id) or {}
                selected_floor = float(selected_room.get("floor_number") or 1)
                if (not str(room_id).startswith("elevator_shaft")
                        and not ("transport_device" in {str(value).lower() for value in (parent_item.get("capabilities") or ())})):
                    position["y"] = max(0.0, selected_floor - 1.0) * 3.2 + 1.6
        # A transport car is a positional container, not a room. Once the
        # agent crosses its footprint, make that relationship canonical so
        # the car's runtime transform carries the agent between floors.
        # Prefer the authoritative room carried by the agent state when the
        # client has only sent horizontal deltas. Its Y coordinate may still
        # be from the original spawn floor until the transport projection
        # returns, while the previous room already identifies the landing.
        transport_room = previous_room_id or room_id
        transport_id = self._transport_container_for_position(state["position"], room_id=transport_room)
        if transport_id:
            # Do not let the overlapping 2D landing room replace the `in`
            # relation before the cabin footprint test runs. That race was
            # the source of passengers being left at 1F after travelling.
            self.move_node(agent_id, transport_id, "in")
            state["room_id"] = str((self.nodes.get(transport_id) or {}).get("states", {}).get("current_floor") or room_id)
        elif current_parent and "transport_device" in {
            str(value).lower() for value in (self.nodes.get(current_parent) or {}).get("capabilities", ())
        }:
            # Leaving the car is a topology transition, not merely a 2D
            # footprint test. At a shared XY footprint the shaft and landing
            # can both match the point, so use the car's settled current_floor
            # as the authoritative landing room and replace the position edge
            # immediately. This prevents the next interaction from seeing the
            # player still inside the shaft.
            transport_states = (self.nodes.get(current_parent) or {}).get("states") or {}
            landing_id = str(transport_states.get("current_floor") or room_id or "")
            if landing_id in self.nodes and str((self.nodes.get(landing_id) or {}).get("node_type") or "") == "room":
                logger.info(
                    "elevator passenger exit agent=%s car=%s current_floor=%s current_height=%s detected_room=%s position=%s",
                    agent_id, current_parent, landing_id,
                    transport_states.get("current_height"), room_id, position,
                )
                state["room_id"] = landing_id
                self.move_node(agent_id, landing_id, "at")
        elif room_id:
            state["room_id"] = room_id
            self.move_node(agent_id, room_id, "at")
        return copy.deepcopy(state)

    def _transport_container_for_position(self, position: dict[str, Any], room_id: str = "") -> str:
        """Return the transport object whose current cabin contains a point.

        Geometry comes from the authored layout and node dimensions; no
        elevator-specific id or scene coordinate is used here.
        """
        layout = self.metadata.get("layout") or {}
        rooms = layout.get("rooms") if isinstance(layout, dict) else {}
        objects = layout.get("objects") if isinstance(layout, dict) else {}
        if not isinstance(rooms, dict) or not isinstance(objects, dict):
            return ""
        px, pz, py = (float(position.get(key) or 0.0) for key in ("x", "z", "y"))
        for node_id, item in self.nodes.items():
            if "transport_device" not in {str(value).lower() for value in (item.get("capabilities") or ())}:
                continue
            placement = objects.get(node_id) if isinstance(objects.get(node_id), dict) else {}
            room = rooms.get(placement.get("room_id")) if isinstance(placement, dict) else None
            if not isinstance(room, dict):
                continue
            grid = float(layout.get("grid_size") or 0.1)
            dimensions = item.get("dimensions_cm") or item.get("bounds_cm") or []
            width = float(placement.get("width_cm") or (dimensions[0] if len(dimensions) > 0 else 0.0)) / 100.0
            depth = float(placement.get("depth_cm") or (dimensions[1] if len(dimensions) > 1 else 0.0)) / 100.0
            height = float(placement.get("height_cm") or (dimensions[2] if len(dimensions) > 2 else 0.0)) / 100.0
            if width <= 0 or depth <= 0 or height <= 0:
                continue
            center_x = (float(room.get("grid_x") or 0.0) + float(room.get("width_cells") or 0.0) / 2.0) * grid
            center_z = (float(room.get("grid_y") or 0.0) + float(room.get("depth_cells") or 0.0) / 2.0) * grid
            states = item.get("states") if isinstance(item.get("states"), dict) else {}
            floor_height = float(states.get("current_height") or 0.0)
            # Include the doorway threshold and the player's capsule radius;
            # using an inset footprint made entry depend on the exact final
            # movement sample and intermittently left passengers in the
            # landing room.
            if (abs(px - center_x) <= width / 2.0 + 0.12
                    and abs(pz - center_z) <= depth / 2.0 + 0.12
                    and floor_height - 0.15 <= py <= floor_height + height + 0.15):
                return str(node_id)
        return ""

    def _can_cross_rooms(self, source_room: str, target_room: str) -> bool:
        if not source_room or not target_room or target_room not in self.adjacent_rooms(source_room):
            return False
        pair = {source_room, target_room}
        doors = [item for item in self.nodes.values() if str(item.get("semantic_type") or "").lower() == "door"]
        relevant = [item for item in doors if pair.issubset({str(room) for room in item.get("connected_rooms") or []})]
        if not relevant:
            return True
        # Door nodes are the sole runtime authority.  Do not use Python's
        # generic truthiness here: a legacy/string value such as ``"false"``
        # must never make a closed door passable.
        def state_is_open(item: dict[str, Any]) -> bool:
            value = (item.get("states") or {}).get("is_open")
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)) and value in (0, 1):
                return bool(value)
            return str(value or "").strip().lower() in {"true", "open", "opened", "1"}

        return any(state_is_open(item) for item in relevant)

    def _validate_node_states(self) -> None:
        allowed = set(DISCRETE_STATE_SPACE)
        invalid = [
            f"{node_id}.{state_name}"
            for node_id, node in sorted(self.nodes.items())
            for state_name in sorted(
                set(node.get("states") or {})
                - allowed
                - (
                    TRANSPORT_RUNTIME_STATE_SPACE
                    if "transport_device" in {
                        str(value).lower() for value in (node.get("capabilities") or ())
                    }
                    else set()
                )
            )
        ]
        if invalid:
            preview = ", ".join(invalid[:20])
            suffix = "" if len(invalid) <= 20 else f", ... ({len(invalid)} total)"
            raise ValueError(f"states outside DISCRETE_STATE_SPACE: {preview}{suffix}")

    def _replace_position_edge(self, node_id: str, parent_id: str, relation: str) -> None:
        self.edges[:] = [
            edge for edge in self.edges
            if not (str(edge.get("target_id") or "") == node_id and str(edge.get("relation") or "") in POSITION_RELATIONS)
        ]
        self.edges.append(Edge(parent_id, node_id, relation, {"canonical": True}).to_dict())

    def refresh_indices(self) -> None:
        parent_of: dict[str, str] = {}
        relation_of: dict[str, str] = {}
        for edge in self.edges:
            relation = str(edge.get("relation") or "").lower()
            source = str(edge.get("source_id") or "")
            target = str(edge.get("target_id") or "")
            if (relation in POSITION_RELATIONS or relation == "structure") and source in self.nodes and target in self.nodes:
                parent_of[target] = source
                relation_of[target] = relation
        current_parent = getattr(self, "parent_of", {})
        current_relation = getattr(self, "relation_of", {})
        current_parent.clear()
        current_parent.update(parent_of)
        current_relation.clear()
        current_relation.update(relation_of)
        self.parent_of = _RuntimeIndex(current_parent)
        self.relation_of = _RuntimeIndex(current_relation)
        room_of = {node_id: self.room_for(node_id) for node_id in self.nodes}
        self.room_of = _RuntimeIndex(room_of)
        controls = [edge for edge in self.edges if str(edge.get("relation") or "").lower() == "controls"]
        rooms = [edge for edge in self.edges if str(edge.get("relation") or "").lower() in ROOM_CONNECTIVITY_RELATIONS]
        current_controls = getattr(self, "control_edges", [])
        current_room_edges = getattr(self, "room_edges", [])
        current_controls[:] = controls
        current_room_edges[:] = rooms
        self.control_edges = current_controls
        self.room_edges = current_room_edges

    def commit_relationship_indices(self) -> None:
        """Rebuild disposable relationship indices from canonical edges."""
        for node in self.nodes.values():
            node.pop("parent", None)
            node.pop("runtime_relation", None)
            node.pop("inventory", None)
        self.refresh_indices()

    def room_for(self, node_id: str) -> str:
        current = self.resolve_id(str(node_id))
        seen: set[str] = set()
        while current and current not in seen:
            seen.add(current)
            item = self.nodes.get(current) or {}
            if str(item.get("node_type") or "") == "room":
                return current
            positional_parent = self.parent_of.get(current, "")
            if positional_parent:
                current = positional_parent
                continue
            # Components are not spatially `in` their host. Their room is
            # inherited through the immutable structure tree instead.
            structure_edge = next((edge for edge in self.edges
                                   if str(edge.get("relation") or "").lower() == "structure"
                                   and str((edge.get("properties") or {}).get("child") or edge.get("target_id") or "") == current), None)
            if structure_edge:
                props = structure_edge.get("properties") if isinstance(structure_edge.get("properties"), dict) else {}
                current = str(props.get("parent") or structure_edge.get("source_id") or "")
            else:
                current = ""
        return ""

    def state_for_rules(self) -> dict[str, Any]:
        return {
            "_graph": self,
            "nodes": self.nodes,
            "edges": self.edges,
            "world_state": self.world_state,
            "parent_of": self.parent_of,
            "relation_of": self.relation_of,
            "room_of": self.room_of,
            "control_edges": self.control_edges,
            "room_edges": self.room_edges,
            "processes": self.world_state.setdefault("processes", []),
        }

    def node(self, node_id: str) -> dict[str, Any]:
        return self.nodes.get(self.resolve_id(str(node_id))) or {}

    def nodes_by_semantic(self, semantic_type: str, room_id: str = "") -> list[str]:
        return [
            node_id for node_id, item in self.nodes.items()
            if str(item.get("semantic_type") or "") == semantic_type
            and (not room_id or self.room_of.get(node_id) == room_id)
        ]

    def adjacent_rooms(self, room_id: str) -> set[str]:
        adjacent: set[str] = set()
        for edge in self.room_edges:
            source = str(edge.get("source_id") or "")
            target = str(edge.get("target_id") or "")
            if source == room_id:
                adjacent.add(target)
            if target == room_id:
                adjacent.add(source)
        return adjacent

    def target_reachable_from_room(self, target_id: str, room_id: str) -> bool:
        target = self.node(target_id)
        return bool(room_id) and (
            self.room_of.get(target_id) == room_id
            or room_id in {str(item) for item in target.get("connected_rooms") or []}
        )

    def has_structural_door_between(self, room_a: str, room_b: str) -> bool:
        pair = {room_a, room_b}
        return any(
            str(item.get("door_kind") or "") == "structural"
            and pair.issubset({str(room_id) for room_id in item.get("connected_rooms") or []})
            for item in self.nodes.values()
        )

    def log(self, event_type: str, detail: str, **payload: Any) -> None:
        event = {"step": int(self.world_state.get("step") or 0), "type": event_type, "detail": detail}
        event.update(payload)
        self.world_state.setdefault("event_log", []).append(event)

    def move_node(self, node_id: str, parent_id: str, relation: str) -> None:
        node_id, parent_id = self.resolve_id(node_id), self.resolve_id(parent_id)
        if node_id not in self.nodes or parent_id not in self.nodes:
            return
        self._replace_position_edge(str(node_id), str(parent_id), str(relation))
        self.refresh_indices()

    def add_edge(self, source_id: str, target_id: str, relation: str, properties: dict[str, Any] | None = None) -> dict[str, Any]:
        source_id, target_id, relation = self.resolve_id(source_id), self.resolve_id(target_id), str(relation).lower()
        if source_id not in self.nodes or target_id not in self.nodes:
            raise KeyError(f"edge endpoints must exist: {source_id}, {target_id}")
        if relation in POSITION_RELATIONS:
            self._replace_position_edge(target_id, source_id, relation)
        elif any(str(edge.get("source_id")) == source_id and str(edge.get("target_id")) == target_id and str(edge.get("relation")) == relation for edge in self.edges):
            return next(edge for edge in self.edges if str(edge.get("source_id")) == source_id and str(edge.get("target_id")) == target_id and str(edge.get("relation")) == relation)
        else:
            self.edges.append(Edge(source_id, target_id, relation, dict(properties or {})).to_dict())
        self.refresh_indices()
        return next(edge for edge in self.edges if str(edge.get("source_id")) == source_id and str(edge.get("target_id")) == target_id and str(edge.get("relation")) == relation)

    def remove_edge(self, source_id: str, target_id: str, relation: str) -> bool:
        source_id, target_id = self.resolve_id(source_id), self.resolve_id(target_id)
        before = len(self.edges)
        self.edges[:] = [edge for edge in self.edges if not (str(edge.get("source_id")) == str(source_id) and str(edge.get("target_id")) == str(target_id) and str(edge.get("relation")) == str(relation).lower())]
        self.refresh_indices()
        return len(self.edges) != before

    def replace_position_edge(self, object_id: str, parent_id: str, relation: str) -> None:
        self._replace_position_edge(self.resolve_id(object_id), self.resolve_id(parent_id), str(relation).lower())
        self.refresh_indices()

    def set_state(self, node_id: str, state_name: str, value: Any, *, source: str = "world") -> None:
        node_id = self.resolve_id(node_id)
        if node_id not in self.nodes:
            raise KeyError(f"unknown node: {node_id}")
        self.set_node_states(str(node_id), **{str(state_name): copy.deepcopy(value)})
        self.log("state_changed", f"{node_id}.{state_name} changed", node_id=str(node_id), state=str(state_name), value=copy.deepcopy(value), source=source)

    def spawn_node(self, node: Node | dict[str, Any]) -> dict[str, Any]:
        record = node.to_dict() if isinstance(node, Node) else copy.deepcopy(node)
        editor_id = str(record.get("editor_id") or record.get("id") or "")
        if not editor_id or editor_id in self.runtime_id_by_editor_id:
            raise ValueError(f"editor id is missing or already exists: {editor_id}")
        runtime_id = f"{self.run_id}:{editor_id}"
        record.update({"id": editor_id, "editor_id": editor_id, "runtime_id": runtime_id})
        self.runtime_id_by_editor_id[editor_id] = runtime_id
        self.editor_id_by_runtime_id[runtime_id] = editor_id
        self.nodes[editor_id] = record
        self.refresh_indices()
        return self.nodes[node_id]

    def remove_node(self, node_id: str) -> None:
        node_id = self.resolve_id(node_id)
        if node_id not in self.nodes:
            return
        editor_id = self.editor_id_by_runtime_id.pop(node_id, "")
        if editor_id:
            self.runtime_id_by_editor_id.pop(editor_id, None)
            self.nodes.aliases.pop(editor_id, None)
        self.nodes.pop(node_id)
        self.edges[:] = [edge for edge in self.edges if str(edge.get("source_id")) != node_id and str(edge.get("target_id")) != node_id]
        self.refresh_indices()

    def set_node_states(self, node_id: str, **updates: Any) -> None:
        if invalid := sorted(set(updates) - set(DISCRETE_STATE_SPACE)):
            raise ValueError(f"{node_id} received states outside DISCRETE_STATE_SPACE: {invalid}")
        if node_id in self.nodes:
            self.nodes[node_id].setdefault("states", {}).update(updates)

    def held_by(self, agent_id: str) -> str:
        agent_id = self.editor_id_by_runtime_id.get(self.resolve_id(agent_id), str(agent_id))
        return next((
            node_id for node_id, parent_id in self.parent_of.items()
            if parent_id == agent_id and str(self.relation_of.get(node_id) or "").startswith("held_by")
        ), "")

    def sync_runtime_edges(self) -> None:
        self.commit_relationship_indices()

    def execute(self, action: dict[str, Any], *, step: int = 0):
        from ..action_executor import ActionExecutor

        return ActionExecutor(self).execute(action, step=step)

    def run(self, operation):
        from ..action_executor import ActionExecutor

        return ActionExecutor(self).run(operation)

    def to_scene(self) -> dict[str, Any]:
        self.commit_relationship_indices()
        self.world_state["transition_log"] = transition_log(self.world_state.get("event_log") or [])
        snapshots = []
        for item in self.nodes.values():
            snapshot = copy.deepcopy(item)
            snapshot["joint_states"] = self._joint_states_for(item)
            # Recompute the protocol transform on every snapshot. This lets
            # runtime agent motion and held_by attachments override authored
            # editor transforms while preserving static transforms for other
            # nodes through _world_transform_for.
            snapshot["world_transform"] = self._world_transform_for(snapshot)
            snapshot["transform_space"] = "graphworld_z_up"
            snapshot["transform_origin"] = self._transform_origin_for(snapshot)
            storage_mode = str(snapshot.get("storage_mode") or "").lower()
            snapshot.setdefault("visibility", "hidden" if storage_mode == "hidden" else "visible")
            snapshot.setdefault("collision_enabled", storage_mode != "hidden")
            snapshot["visual_cues"] = visual_cues(snapshot)
            snapshots.append(snapshot)
        return {
            **copy.deepcopy(self.metadata),
            "scene_name": self.scene_name,
            "coordinate_system": {
                "units": "m",
                "handedness": "right",
                "up_axis": "z",
                "rotation": "quaternion_xyzw",
            },
            "world_state": copy.deepcopy(self.world_state),
            "nodes": snapshots,
            "edges": copy.deepcopy(self.edges),
            "processes": copy.deepcopy(self.world_state.get("processes", [])),
        }

    def _transform_origin_for(self, item: dict[str, Any]) -> str:
        node_id = str(item.get("id") or "")
        if node_id in (self.world_state.get("agents") or {}):
            return "held_runtime" if str(self.relation_of.get(node_id) or "").startswith("held_by") else "runtime"
        if any(
            str(edge.get("relation") or "").lower() == "structure"
            and str((edge.get("properties") or {}).get("child") or edge.get("target_id") or "") == node_id
            for edge in self.edges
        ):
            return "structure"
        if isinstance(item.get("world_transform"), dict) or isinstance(item.get("transform"), dict):
            return "authored"
        return "layout_center"

    def _joint_states_for(
        self,
        item: dict[str, Any],
        *,
        nodes: dict[str, dict[str, Any]] | None = None,
        edges: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Project component state cards onto the owning object's joints."""
        nodes = self.nodes if nodes is None else nodes
        edges = self.edges if edges is None else edges
        states = item.get("joint_states") if isinstance(item.get("joint_states"), dict) else {}
        result = copy.deepcopy(states)
        parent_id = str(item.get("id") or "")
        for edge in edges:
            props = edge.get("properties") if isinstance(edge.get("properties"), dict) else {}
            if str(edge.get("relation") or "").lower() != "structure":
                continue
            if str(props.get("parent") or edge.get("source_id") or "") != parent_id:
                continue
            child_id = str(props.get("child") or edge.get("target_id") or "")
            joint_id = str(edge.get("id") or f"{parent_id}->{child_id}")
            if joint_id in result or child_id in result:
                continue
            child = nodes.get(child_id) or {}
            child_states = child.get("states") if isinstance(child.get("states"), dict) else {}
            value = child_states.get("joint_position", child_states.get("position"))
            if value is None and isinstance(child_states.get("is_open"), bool):
                if not child_states["is_open"]:
                    value = 0.0
                else:
                    joint_type = str(props.get("joint_type") or "fixed").lower()
                    limits = props.get("limits") if isinstance(props.get("limits"), dict) else {}
                    upper = limits.get("upper", limits.get("max"))
                    try:
                        value = float(upper) if upper is not None else (0.3 if joint_type == "prismatic" else 1.5707963267948966)
                    except (TypeError, ValueError):
                        value = 0.0
            if value is not None:
                result[joint_id] = value
        return result

    def _world_transform_for(self, item: dict[str, Any]) -> dict[str, list[float]]:
        """Return a protocol transform without owning renderer state."""
        node_id = str(item.get("id") or "")
        # Transport objects remain ordinary Object nodes. Their process owns
        # the discrete floor state; this projection turns that state into the
        # continuous car translation consumed by render adapters.
        if "transport_device" in {str(value).lower() for value in (item.get("capabilities") or ())}:
            state = item.get("states") if isinstance(item.get("states"), dict) else {}
            floor_id = str(state.get("current_floor") or item.get("floor_id") or "")
            elevations = item.get("floor_elevations") or item.get("elevations") or {}
            if floor_id and isinstance(elevations, dict) and floor_id in elevations:
                existing = item.get("world_transform") or item.get("transform") or {}
                # The elevator's horizontal anchor is authored layout data.
                # Never reuse a stale runtime/world transform for XY: only the
                # transport process may change the vertical coordinate.
                layout = self.metadata.get("layout") or {}
                placement = (layout.get("objects") or {}).get(node_id, {}) if isinstance(layout, dict) else {}
                room = (layout.get("rooms") or {}).get(placement.get("room_id"), {}) if isinstance(layout, dict) and isinstance(placement, dict) else {}
                width = float(placement.get("width_cm") or 0.0) / 100.0 if isinstance(placement, dict) else 0.0
                depth = float(placement.get("depth_cm") or 0.0) / 100.0 if isinstance(placement, dict) else 0.0
                grid = float(layout.get("grid_size") or 0.1) if isinstance(layout, dict) else 0.1
                if isinstance(placement, dict) and isinstance(room, dict):
                    x = (float(room.get("grid_x") or 0.0) + float(room.get("width_cells") or 0.0) / 2.0) * grid
                    y_web = (float(room.get("grid_y") or 0.0) + float(room.get("depth_cells") or 0.0) / 2.0) * grid
                    base = [x, -y_web, 0.0]
                else:
                    base = [0.0, 0.0, 0.0]
                # During travel, current_height is the authoritative
                # continuous car elevation; at rest it equals the floor's
                # configured elevation.
                try:
                    base[2] = float(state.get("current_height")) if state.get("current_height") is not None else float(elevations[floor_id])
                except (TypeError, ValueError):
                    base[2] = float(elevations[floor_id])
                return {
                    "position": base,
                    "rotation": list(existing.get("rotation") or [0.0, 0.0, 0.0, 1.0]) if isinstance(existing, dict) else [0.0, 0.0, 0.0, 1.0],
                    "scale": list(existing.get("scale") or [1.0, 1.0, 1.0]) if isinstance(existing, dict) else [1.0, 1.0, 1.0],
                }
        parent_id = self.parent_of.get(node_id)
        relation = str(self.relation_of.get(node_id) or "").lower()
        parent = self.nodes.get(str(parent_id)) if parent_id else None
        if parent and relation in {"in", "inside"} and "transport_device" in {
            str(value).lower() for value in (parent.get("capabilities") or ())
        }:
            parent_transform = Transform.from_dict(self._world_transform_for(parent))
            local_value = item.get("transport_local_transform")
            if not isinstance(local_value, dict):
                authored = item.get("world_transform") or item.get("transform")
                if not isinstance(authored, dict):
                    runtime_agent = (self.world_state.get("agents") or {}).get(node_id)
                    if isinstance(runtime_agent, dict) and isinstance(runtime_agent.get("position"), dict):
                        position = runtime_agent["position"]
                        authored = {
                            "position": [
                                float(position.get("x") or 0.0),
                                -float(position.get("z") or 0.0),
                                float(position.get("y") or 0.0),
                            ],
                            "rotation": [0.0, 0.0, 0.0, 1.0],
                            "scale": [1.0, 1.0, 1.0],
                        }
                if isinstance(authored, dict):
                    authored_transform = Transform.from_dict(authored)
                    local_value = Transform(
                        position=tuple(authored_transform.position[index] - parent_transform.position[index] for index in range(3)),
                        rotation=authored_transform.rotation,
                        scale=authored_transform.scale,
                    ).to_dict()
                else:
                    local_value = IDENTITY_TRANSFORM.to_dict()
                item["transport_local_transform"] = copy.deepcopy(local_value)
            return parent_transform.compose(Transform.from_dict(local_value)).to_dict()
        agent = (self.world_state.get("agents") or {}).get(node_id)
        if isinstance(agent, dict) and isinstance(agent.get("position"), dict):
            position = agent["position"]
            return {
                # Runtime movement keeps the historical Web basis (x/z on
                # the floor, y as height). Publish the protocol basis (x/y
                # on the floor, z up) without mutating that internal state.
                "position": [float(position.get("x") or 0.0), -float(position.get("z") or 0.0), float(position.get("y") or 0.0)],
                "rotation": [0.0, 0.0, 0.0, 1.0],
                "scale": [1.0, 1.0, 1.0],
            }
        # A held object is rigidly attached to the selected agent hand.  The
        # renderer may apply the hand anchor locally, but the semantic
        # snapshot must still expose the current runtime owner transform
        # instead of the stale editor/layout transform.
        parent_id = self.parent_of.get(node_id)
        relation = str(self.relation_of.get(node_id) or "")
        if parent_id and relation.startswith("held_by"):
            parent_agent = (self.world_state.get("agents") or {}).get(str(parent_id))
            if isinstance(parent_agent, dict) and isinstance(parent_agent.get("position"), dict):
                position = parent_agent["position"]
                return {
                    "position": [float(position.get("x") or 0.0), -float(position.get("z") or 0.0), float(position.get("y") or 0.0)],
                    "rotation": [0.0, 0.0, 0.0, 1.0],
                    "scale": [1.0, 1.0, 1.0],
                }
        structure = self._structure_transform(node_id)
        if structure is not None:
            return structure.to_dict()
        existing = item.get("world_transform") or item.get("transform")
        if isinstance(existing, dict):
            return copy.deepcopy(existing)
        layout = self.metadata.get("layout") or {}
        placement = (layout.get("objects") or {}).get(node_id, {}) if isinstance(layout, dict) else {}
        if isinstance(placement, dict):
            width = float(placement.get("width_cm") or 0.0) / 100.0
            depth = float(placement.get("depth_cm") or 0.0) / 100.0
            height = float(placement.get("height_cm") or 0.0) / 100.0
            # Legacy layout values are bottom-surface anchors in the Web
            # basis. Convert them to the protocol root origin at the asset
            # center; explicit authored transforms above remain authoritative.
            x = float(placement.get("x_cm") or 0.0) / 100.0 + width / 2.0
            y = -(float(placement.get("y_cm") or 0.0) / 100.0 + depth / 2.0)
            # Layout coordinates use one canonical convention for every
            # object: x/y locate the footprint and z_cm is the bottom height.
            # Placement mode must not change the transform; wall-mounted
            # assets are authored at their intended z_cm like any other asset.
            z = float(placement.get("z_cm") or 0.0) / 100.0 + height / 2.0
            position = [
                x,
                y,
                z,
            ]
            return {
                "position": position,
                "rotation": [0.0, 0.0, 0.0, 1.0],
                "scale": [1.0, 1.0, 1.0],
            }
        return {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0, 1.0], "scale": [1.0, 1.0, 1.0]}

    def _structure_transform(self, node_id: str, active: set[str] | None = None) -> Transform | None:
        """Resolve a component's final transform from immutable structure edges."""
        active = set(active or ())
        if node_id in active:
            return None
        edge = next((edge for edge in self.edges if str(edge.get("relation") or "").lower() == "structure"
                     and str((edge.get("properties") or {}).get("child") or edge.get("child") or "") == node_id), None)
        if not edge:
            return None
        props = edge.get("properties") if isinstance(edge.get("properties"), dict) else {}
        parent_id = str(props.get("parent") or edge.get("parent") or "")
        parent = self.nodes.get(parent_id)
        child = self.nodes.get(node_id)
        if not parent or not child:
            return None
        active.add(node_id)
        parent_transform = self._world_transform_for(parent)
        result = Transform.from_dict(parent_transform)
        origin = Transform.from_dict(props.get("origin"))
        motion = _joint_motion_transform(
            str(props.get("joint_type") or "fixed"),
            props.get("axis") or (0.0, 0.0, 1.0),
            self._joint_position(parent, node_id, str(edge.get("id") or f"{parent_id}->{node_id}")),
        )
        # A component may add a local visual offset; it is not a second world
        # transform and therefore composes only after the joint motion.
        local = Transform.from_dict(child.get("local_transform")) if isinstance(child.get("local_transform"), dict) else IDENTITY_TRANSFORM
        return result.compose(origin).compose(motion).compose(local)

    def _joint_position(self, parent: dict[str, Any], child_id: str, joint_id: str) -> float:
        states = self._joint_states_for(parent)
        value = states.get(joint_id, states.get(child_id, 0.0)) if isinstance(states, dict) else 0.0
        if isinstance(value, dict):
            value = value.get("position", value.get("value", 0.0))
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


__all__ = ["World"]


def _joint_motion_transform(joint_type: str, axis: Any, position: float) -> Transform:
    values = tuple(float(value) for value in axis) if isinstance(axis, (list, tuple)) and len(axis) >= 3 else (0.0, 0.0, 1.0)
    length = math.sqrt(sum(value * value for value in values)) or 1.0
    unit = tuple(value / length for value in values)
    if joint_type == "prismatic":
        return Transform(position=tuple(value * position for value in unit))
    if joint_type in {"revolute", "continuous"}:
        half = position / 2.0
        sine = math.sin(half)
        return Transform(rotation=(unit[0] * sine, unit[1] * sine, unit[2] * sine, math.cos(half)))
    return IDENTITY_TRANSFORM
