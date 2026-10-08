"""Long-lived scene simulation sessions."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from threading import RLock
from uuid import uuid4
from typing import Any

from backend.app.schemas.scene import SimulationDispatchRequest, SimulationSessionResponse, SimulationStartRequest
from backend.generation.assets.object_library import materialize
from backend.app.runtime.scene_importer import normalize_legacy_scene
from backend.runtime.input_adapter import ActionResolver, InteractionRequest
from backend.runtime.action_executor import ActionExecutor
from backend.runtime.world import World
from backend.runtime.time import advance_time
from backend.runtime.scene_preparation import ensure_demo_elevator, ensure_laundry_detergent_station
from backend.app.runtime.scene_layout import ensure_scene_layout

logger = logging.getLogger(__name__)


def _resolve_actor_id(graph: World, requested_id: str) -> str:
    """Resolve the interactive actor against the actual scene graph.

    Editor scenes do not share a required robot identifier. Older snapshots
    may use ``human``, ``robot`` or ``agent`` node types, so a hard-coded
    fallback such as ``robot_01`` is invalid.
    """
    requested = str(requested_id or "")
    if requested and graph.node(requested):
        return requested
    for node_id, item in graph.nodes.items():
        node_type = str(item.get("node_type") or "").lower()
        semantic = str(item.get("semantic_type") or "").lower()
        if node_type in {"agent", "robot", "human"} or semantic in {"agent", "robot", "human"}:
            return str(node_id)
    return requested


def _ensure_simulation_actor(graph: World, requested_id: str, target_id: str) -> str:
    actor_id = _resolve_actor_id(graph, requested_id)
    if actor_id and graph.node(actor_id):
        return actor_id

    actor_id = "__simulation_player__"
    graph.nodes[actor_id] = {
        "id": actor_id,
        "editor_id": actor_id,
        "node_type": "agent",
        "semantic_type": "robot",
        "name": "Simulation Player",
        "capabilities": ["reachable"],
        "interactive_actions": ["move", "pick", "place", "press", "open", "close"],
        "states": {},
        # First-person center-ray interactions often hit a bed/floor surface
        # slightly beyond the hand marker.  This is the simulation player's
        # control envelope; authored agents keep their declared reach.
        "reach_distance_m": 2.8,
    }

    target_room = graph.room_of.get(str(target_id), "")
    if not target_room:
        target_room = next((node_id for node_id, item in graph.nodes.items() if str(item.get("node_type") or "") == "room"), "")
    if target_room:
        graph.edges.append({
            "source_id": target_room,
            "target_id": actor_id,
            "relation": "at",
            "edge_type": "spatial_edge",
            "category": "spatial",
            "properties": {"runtime_only": True},
        })
    graph.refresh_indices()
    return actor_id


@dataclass
class _SimulationSession:
    world: World
    actor_id: str
    lock: RLock
    revision: int = 0
    time_seconds: float = 0.0
    processed_event_ids: set[str] = None
    last_sequence: int = -1

    def __post_init__(self) -> None:
        if self.processed_event_ids is None:
            self.processed_event_ids = set()

    def snapshot(self, simulation_id: str) -> dict[str, Any]:
        scene = self.world.to_scene()
        scene.update({
            "session_id": simulation_id,
            "scene_id": scene.get("scene_name", ""),
            "revision": self.revision,
            "time_seconds": self.time_seconds,
            "events": copy.deepcopy(self.world.world_state.get("event_log", [])),
        })
        return scene


class SimulationWorldService:
    """Long-lived simulation worlds.

    An interactive run owns one World instance from start until stop. Inputs
    mutate that instance; no request carries a scene snapshot back into the
    runtime.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _SimulationSession] = {}
        self._lock = RLock()
        self.resolver = ActionResolver()

    def start(self, request: SimulationStartRequest) -> SimulationSessionResponse:
        source = materialize(normalize_legacy_scene(copy.deepcopy(request.source_json)))
        # The run must receive the same generated elevator graph as the
        # editor: landing buttons, cabin controls, hall-door links, and their
        # layout anchors are runtime truth, not renderer-only additions.
        if str(source.get("scene_name") or "").startswith("simple_home"):
            ensure_demo_elevator(source)
            ensure_laundry_detergent_station(source)
            # Keep the runtime source identical to the editor graph after
            # demo elevator nodes are added. In particular, hall call
            # buttons must exist in both nodes and layout.objects before the
            # World snapshot is created.
            source = ensure_scene_layout(source)
        world = World(source)
        actor_id = _ensure_simulation_actor(world, request.actor_id, "")
        world.ensure_agent_state(actor_id)
        simulation_id = f"sim_{uuid4().hex}"
        session = _SimulationSession(world, actor_id, RLock())
        with self._lock:
            self._sessions[simulation_id] = session
        door = world.node("door_entrance")
        logger.info("simulation start state: id=%s door_entrance.is_open=%r", simulation_id, (door or {}).get("states", {}).get("is_open"))
        return SimulationSessionResponse(simulation_id=simulation_id, snapshot=session.snapshot(simulation_id))

    def dispatch(self, request: SimulationDispatchRequest) -> SimulationSessionResponse:
        session = self._sessions.get(request.simulation_id)
        if session is None:
            raise KeyError(f"unknown simulation: {request.simulation_id}")
        with session.lock:
            before_door = session.world.node("door_entrance")
            logger.info(
                "simulation dispatch input: id=%s input=%s target=%s door_entrance.is_open=%r",
                request.simulation_id,
                request.input,
                request.target_id,
                (before_door or {}).get("states", {}).get("is_open"),
            )
            if request.event:
                event_id = str(request.event.get("event_id") or "")
                sequence = int(request.event.get("sequence") or 0)
                if event_id and event_id in session.processed_event_ids:
                    return SimulationSessionResponse(
                        simulation_id=request.simulation_id,
                        applied=False,
                        failures=["duplicate input event"],
                        snapshot=session.snapshot(request.simulation_id),
                    )
                # Event sequences are strictly monotonic within a session.
                # Duplicate event ids are handled first so retransmitting the
                # same event remains an explicit, deterministic response.
                if sequence <= session.last_sequence:
                    return SimulationSessionResponse(
                        simulation_id=request.simulation_id,
                        applied=False,
                        failures=["stale input sequence"],
                        snapshot=session.snapshot(request.simulation_id),
                    )
                if event_id:
                    session.processed_event_ids.add(event_id)
                session.last_sequence = max(session.last_sequence, sequence)
            base_revision = session.revision
            actor_id = session.actor_id
            failures: list[str] = []
            action: dict[str, Any] | None = None
            delta: dict[str, Any] = {}
            if request.input == "move_step":
                raw = str(request.direction or "").replace(",", " ").split()
                try:
                    dx, dz = (float(raw[0]), float(raw[1])) if len(raw) >= 2 else (0.0, 0.0)
                except ValueError:
                    dx, dz = 0.0, 0.0
                moved_state: dict[str, Any] = {}

                def apply_move(_: dict[str, Any]) -> None:
                    moved_state.update(session.world.move_agent(actor_id, dx, dz, request.elapsed_seconds))

                # Movement is a runtime mutation too.  Keep it inside the
                # same transaction boundary as semantic actions so malformed
                # input or a future collision adapter can roll it back.
                ActionExecutor(session.world).run(apply_move)
                agent_state = copy.deepcopy(moved_state)
                applied = True
                delta = {
                    # Compatibility projection for current Web clients.
                    "agent": {actor_id: agent_state},
                    "changes": [{
                        "change_type": "node_updated",
                        "change_id": f"move_{actor_id}_{session.revision + 1}",
                        "source": "action:move_step",
                        "payload": {
                            "node_id": actor_id,
                            "runtime_state": copy.deepcopy(agent_state),
                            "agent_state": copy.deepcopy(agent_state),
                            "world_transform": {
                                "position": [
                                    float(agent_state["position"].get("x") or 0.0),
                                    -float(agent_state["position"].get("z") or 0.0),
                                    float(agent_state["position"].get("y") or 0.0),
                                ],
                                "rotation": [0.0, 0.0, 0.0, 1.0],
                                "scale": [1.0, 1.0, 1.0],
                            },
                            "transform_space": "graphworld_z_up",
                            "transform_origin": "runtime",
                        },
                    }],
                }
                action = {"agent": actor_id, "action": "move_step", "direction": [dx, dz]}
                session.time_seconds += max(0.0, float(request.elapsed_seconds))
            elif request.input == "input_event":
                # Input lifecycle events are transport-only except for the
                # runtime movement flag.  A movement release must clear the
                # authoritative `moving` state; otherwise a client that stops
                # sending movement samples would leave the agent moving
                # forever in snapshots.
                applied = True
                action = {"agent": actor_id, "action": "input_event"}
                event = request.event or {}
                if (
                    str(event.get("event_type") or "") == "movement"
                    and str(event.get("phase") or "") == "released"
                ):
                    agent_state = session.world.ensure_agent_state(actor_id)
                    remaining_keys = (event.get("payload") or {}).get("active_movement_keys")
                    if not isinstance(remaining_keys, list) or not remaining_keys:
                        agent_state["moving"] = False
                    delta = {
                        "agent": {actor_id: copy.deepcopy(agent_state)},
                        "changes": [{
                            "change_type": "node_updated",
                            "change_id": f"movement_release_{actor_id}_{session.revision + 1}",
                            "source": "input:movement_release",
                            "payload": {
                                "node_id": actor_id,
                                "runtime_state": copy.deepcopy(agent_state),
                                "agent_state": copy.deepcopy(agent_state),
                            },
                        }],
                    }
            elif request.input in {"tick", "wait"}:
                tick_delta = ActionExecutor(session.world).run(
                    lambda state: advance_time(state, request.elapsed_steps)
                )
                applied = True
                delta = tick_delta.to_dict()
                session.time_seconds += max(0.0, float(request.elapsed_steps))
            else:
                resolved = self.resolver.resolve(
                    session.world.state_for_rules(),
                    InteractionRequest(
                        actor_id=actor_id,
                        input=request.input,
                        target_id=request.target_id,
                        target_link_id=str(request.hit.get("link_id") or ""),
                        distance_m=request.distance_m,
                        hit=copy.deepcopy(request.hit),
                        hand=request.hand,
                        event=copy.deepcopy(request.event or {}),
                    ),
                )
                action = copy.deepcopy(resolved.action)
                if action is None:
                    return SimulationSessionResponse(
                        simulation_id=request.simulation_id,
                        applied=False,
                        action=None,
                        failures=list(resolved.failures),
                        snapshot=session.snapshot(request.simulation_id),
                    )
                mutation = ActionExecutor(session.world).execute(action, step=int(session.world.world_state.get("step") or 0))
                applied = mutation.ok
                failures = list(mutation.failures)
                delta = mutation.delta.to_dict()
                after_door = session.world.node("door_entrance")
                logger.info(
                    "simulation dispatch action: id=%s action=%s applied=%s door_entrance.is_open=%r state_changes=%s",
                    request.simulation_id,
                    action,
                    applied,
                    (after_door or {}).get("states", {}).get("is_open"),
                    delta.get("state_changes", []),
                )
            if applied:
                session.revision += 1
                if isinstance(delta, dict):
                    delta.setdefault("session_id", request.simulation_id)
                    delta.setdefault("base_revision", base_revision)
                    delta.setdefault("revision", session.revision)
                    delta.setdefault("time_seconds", session.time_seconds)
            return SimulationSessionResponse(
                simulation_id=request.simulation_id,
                applied=applied,
                action=action,
                failures=failures,
                delta=delta,
                snapshot=session.snapshot(request.simulation_id),
            )

    def stop(self, simulation_id: str) -> None:
        with self._lock:
            self._sessions.pop(simulation_id, None)


simulation_world_service = SimulationWorldService()


__all__ = ["SimulationWorldService", "simulation_world_service"]
