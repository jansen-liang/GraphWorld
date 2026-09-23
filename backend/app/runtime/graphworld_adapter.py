from __future__ import annotations

import copy
from typing import Any

from backend.runtime.agent.planning import candidate_actions
from backend.runtime.camera import camera_spec_for_agent
from backend.runtime.engine import Orchestrator

from backend.app.runtime.schedule import planned_events_for_step
from backend.app.schemas.action import CandidateAction
from backend.app.schemas.observation import Observation
from backend.app.schemas.run import VisibilityMode


def canonical_node_type(node: dict[str, Any]) -> str:
    return str(node.get("node_type") or node.get("type") or node.get("semantic_type") or "")


def ensure_robot_node(raw: dict[str, Any], agent_id: str = "robot_01") -> None:
    nodes = raw.setdefault("nodes", [])
    if any(str(node.get("id") or "") == agent_id for node in nodes if isinstance(node, dict)):
        return
    current_room = str((raw.get("agent") or {}).get("current_room") or "")
    if not current_room:
        current_room = next(
            (
                str(node.get("id") or "")
                for node in nodes
                if isinstance(node, dict) and canonical_node_type(node) == "room"
            ),
            "",
        )
    if not current_room:
        return
    nodes.append(
        {
            "id": agent_id,
            "name": "Robot",
            "name_cn": "机器人",
            "node_type": "robot",
            "semantic_type": "robot",
            "mobility": "agent",
            "states": {},
            "property": {"appearance": "", "physical": "", "operation": ""},
            "affordance_count": 0,
            "parent": current_room,
            "child": [],
            "interactive_actions": [],
            "layout": {},
            "current_location": current_room,
        }
    )
    raw.setdefault("edges", []).append(
        {
            "source_id": current_room,
            "target_id": agent_id,
            "relation": "at",
            "edge_type": "agent_room_edge",
            "category": "containment",
            "properties": {"visualized_from": "web_runtime_adapter"},
        }
    )


def action_id(action: dict[str, Any]) -> str:
    parts = [
        str(action.get("action") or ""),
        str(action.get("target") or ""),
        str(action.get("object") or ""),
    ]
    if action.get("destination_room"):
        parts.append(f"destination={action['destination_room']}")
    return ":".join(parts)


def compact_candidate(action: dict[str, Any]) -> CandidateAction:
    return CandidateAction(
        action_id=action_id(action),
        action_type=str(action.get("action") or ""),
        actor_id=str(action.get("agent") or ""),
        target_id=str(action.get("target") or ""),
        object_id=str(action.get("object") or ""),
        reason=str(action.get("reason") or ""),
        legal=bool(action.get("legal", True)),
        preview=str(action.get("reason") or ""),
        payload=copy.deepcopy(action),
        action_contract=copy.deepcopy(action.get("action_contract") or {}),
    )


class GraphWorldAdapter:
    def __init__(self, source_json: dict[str, Any], *, agent_id: str = "robot_01") -> None:
        self.source_json = copy.deepcopy(source_json)
        self.agent_id = agent_id

    def orchestrator(self) -> Orchestrator:
        raw = copy.deepcopy(self.source_json)
        ensure_robot_node(raw, self.agent_id)
        return Orchestrator(raw)

    def replay_orchestrator(
        self,
        selected_actions: list[dict[str, Any]],
        *,
        visibility_mode: str | VisibilityMode = VisibilityMode.fog_of_war,
    ) -> Orchestrator:
        orchestrator = self.orchestrator()
        for step_index, action in enumerate(selected_actions):
            self.runtime_observation(orchestrator, visibility_mode=visibility_mode)
            human_events = planned_events_for_step(orchestrator.graph.to_scene(), step_index)
            orchestrator.step(
                robot_actions=[copy.deepcopy(action)] if action else [],
                human_events=human_events,
                capture_robot_scene=False,
                capture_scene=False,
            )
        self.runtime_observation(orchestrator, visibility_mode=visibility_mode)
        return orchestrator

    def runtime_observation(
        self,
        orchestrator: Orchestrator,
        *,
        visibility_mode: str | VisibilityMode,
    ) -> dict[str, Any]:
        mode = str(getattr(visibility_mode, "value", visibility_mode))
        if mode == VisibilityMode.full.value:
            raw = orchestrator.graph.to_scene()
            visible_rooms = [
                str(node.get("id") or "")
                for node in raw.get("nodes") or []
                if isinstance(node, dict) and canonical_node_type(node) == "room"
            ]
            observation = {
                "world_state": {
                    **copy.deepcopy(raw.get("world_state") or {}),
                    "visible_rooms": sorted(visible_rooms),
                    "confidence_by_room": {room_id: 1.0 for room_id in visible_rooms},
                },
                "nodes": copy.deepcopy(raw.get("nodes") or []),
                "edges": copy.deepcopy(raw.get("edges") or []),
            }
        elif mode == VisibilityMode.room.value:
            current_room = orchestrator.graph.room_of.get(self.agent_id, "")
            visible_rooms = {current_room} if current_room else set()
            visible_ids = {
                node_id
                for node_id in orchestrator.graph.nodes
                if node_id == self.agent_id
                or node_id in visible_rooms
                or orchestrator.graph.room_of.get(node_id) in visible_rooms
            }
            observation = {
                "scene_name": orchestrator.graph.scene_name,
                "world_state": {
                    **copy.deepcopy(orchestrator.graph.world_state),
                    "visible_rooms": sorted(visible_rooms),
                    "confidence_by_room": {room_id: 1.0 for room_id in visible_rooms},
                },
                "nodes": [copy.deepcopy(orchestrator.graph.nodes[node_id]) for node_id in sorted(visible_ids)],
                "edges": [
                    copy.deepcopy(edge)
                    for edge in orchestrator.graph.edges
                    if str(edge.get("source_id") or "") in visible_ids
                    and str(edge.get("target_id") or "") in visible_ids
                ],
            }
        else:
            observation = orchestrator.perception.robot_view(self.agent_id)
        world_state = observation.setdefault("world_state", {})
        visible_ids = {
            str(item.get("id") or "")
            for item in observation.get("nodes") or []
            if isinstance(item, dict) and item.get("id")
        }
        status_by_node = dict(world_state.get("observation_status_by_node") or {})
        last_seen = {
            str(key): int(value)
            for key, value in (world_state.get("last_seen_step_by_node") or {}).items()
        }
        status_by_room = dict(world_state.get("observation_status_by_room") or {})
        step = int(world_state.get("step") or 0)
        for node_id, node in orchestrator.graph.nodes.items():
            if node_id in visible_ids:
                status_by_node[node_id] = "visible"
                last_seen.setdefault(node_id, step)
            elif node_id not in status_by_node:
                node_room = orchestrator.graph.room_of.get(node_id, "")
                status_by_node[node_id] = "occluded" if node_room in set(world_state.get("visible_rooms") or []) else "unknown"
        for node_id, node in orchestrator.graph.nodes.items():
            if str(node.get("node_type") or "") != "room":
                continue
            status_by_room.setdefault(
                node_id,
                "visible" if node_id in set(world_state.get("visible_rooms") or []) else "unknown",
            )
        world_state["observation_status_by_node"] = status_by_node
        world_state["last_seen_step_by_node"] = last_seen
        world_state["observation_status_by_room"] = status_by_room
        return observation

    def candidate_payloads(
        self,
        orchestrator: Orchestrator,
        *,
        visibility_mode: str | VisibilityMode,
    ) -> list[dict[str, Any]]:
        observation = self.runtime_observation(orchestrator, visibility_mode=visibility_mode)
        return candidate_actions(orchestrator, observation, self.agent_id)

    def observation(
        self,
        orchestrator: Orchestrator,
        *,
        visibility_mode: str | VisibilityMode,
    ) -> Observation:
        mode = str(getattr(visibility_mode, "value", visibility_mode))
        observation = self.runtime_observation(orchestrator, visibility_mode=mode)

        candidates = [
            compact_candidate(item)
            for item in candidate_actions(orchestrator, observation, self.agent_id)
        ]
        world_state = observation.get("world_state") or {}
        observation["camera"] = camera_spec_for_agent(observation, self.agent_id)
        return Observation(
            actor_id=self.agent_id,
            step_index=int(world_state.get("step") or 0),
            visibility_mode=mode,
            visible_rooms=[str(item) for item in world_state.get("visible_rooms") or []],
            visible_nodes=copy.deepcopy(observation.get("nodes") or []),
            visible_edges=copy.deepcopy(observation.get("edges") or []),
            memory_nodes=[],
            unknown_rooms=[],
            confidence_by_room={
                str(key): float(value)
                for key, value in (world_state.get("confidence_by_room") or {}).items()
            },
            observation_status_by_node={
                str(key): str(value)
                for key, value in (world_state.get("observation_status_by_node") or {}).items()
            },
            last_seen_step_by_node={
                str(key): int(value)
                for key, value in (world_state.get("last_seen_step_by_node") or {}).items()
            },
            observation_status_by_room={
                str(key): str(value)
                for key, value in (world_state.get("observation_status_by_room") or {}).items()
            },
            candidate_actions=candidates,
            camera=copy.deepcopy(observation.get("camera") or {}),
        )

    def candidate_by_id(
        self,
        orchestrator: Orchestrator,
        *,
        visibility_mode: str | VisibilityMode,
        selected_action_id: str,
    ) -> dict[str, Any] | None:
        for candidate in self.candidate_payloads(orchestrator, visibility_mode=visibility_mode):
            if action_id(candidate) == selected_action_id:
                return copy.deepcopy(candidate)
        return None
