from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.runtime.agent import fallback_choose_action, llm_choose_action
from backend.runtime.eval import build_matrix_snapshot, matrix_score

from backend.app.core.errors import InvalidStateError, NotFoundError
from backend.app.db.models import Run, RunStep, User
from backend.app.repositories.run_repo import RunRepository
from backend.app.repositories.scene_repo import SceneRepository
from backend.app.runtime.graphworld_adapter import GraphWorldAdapter, action_id
from backend.runtime.camera import validate_interaction_hit
from backend.core.interaction import InteractionRequest as CoreInteractionRequest, resolve_interaction
from backend.app.runtime.schedule import expected_events, planned_events_for_step
from backend.app.schemas.action import ActionRequest, ActionResult
from backend.app.schemas.metrics import MetricPoint, RunMetricsResponse
from backend.app.schemas.observation import Observation
from backend.app.schemas.replay import ReplayResponse, ReplayStepRead
from backend.app.schemas.run import ControlMode, RunCreate, RunCurrentResponse, RunRead, RunStatus, VisibilityMode


def _run_id() -> str:
    return f"run_{uuid4().hex[:16]}"


def _run_read(run: Run) -> RunRead:
    return RunRead(
        id=run.id,
        owner_user_id=run.owner_user_id,
        owner_username=run.owner.username if run.owner else None,
        scene_version_id=run.scene_version_id,
        control_mode=run.control_mode,
        visibility_mode=run.visibility_mode,
        status=run.status,
        current_step=run.current_step,
        config=run.config,
        summary=run.summary,
        artifact_uri=run.artifact_uri,
        error_message=run.error_message,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
    )


def _step_read(step: RunStep) -> ReplayStepRead:
    return ReplayStepRead(
        run_id=step.run_id,
        step_index=step.step_index,
        actor_type=step.actor_type,
        actor_id=step.actor_id,
        observation=step.observation,
        candidate_actions=step.candidate_actions,
        selected_action=step.selected_action,
        action_result=step.action_result,
        world_state_before=step.world_state_before,
        world_state_after=step.world_state_after,
        events=step.events,
        metrics=step.metrics,
        created_at=step.created_at,
    )


def _action_result(payload: dict[str, Any]) -> ActionResult:
    return ActionResult(
        ok=bool(payload.get("ok", False)),
        message=str(payload.get("message") or payload.get("detail") or payload.get("reason") or ""),
        failures=[str(item) for item in payload.get("failures") or payload.get("validation_failures") or []],
        payload=copy.deepcopy(payload),
    )


def _events_since(before_scene: dict[str, Any], after_scene: dict[str, Any]) -> list[dict[str, Any]]:
    before_events = (before_scene.get("world_state") or {}).get("event_log") or []
    after_events = (after_scene.get("world_state") or {}).get("event_log") or []
    return copy.deepcopy(after_events[len(before_events) :])


def _metrics_for_step(
    observation: Observation,
    candidates: list[dict[str, Any]],
    action_result: ActionResult,
    after_scene: dict[str, Any],
    *,
    baseline_scene: dict[str, Any] | None = None,
    before_scene: dict[str, Any] | None = None,
    expected_human_events: tuple[str, ...] = (),
) -> dict[str, Any]:
    world_state = after_scene.get("world_state") or {}
    metrics = {
        "world_step": int(world_state.get("step") or 0),
        "visible_room_count": len(observation.visible_rooms),
        "visible_node_count": len(observation.visible_nodes),
        "memory_node_count": len(observation.memory_nodes),
        "candidate_action_count": len(candidates),
        "action_ok": action_result.ok,
    }
    try:
        current = build_matrix_snapshot(after_scene, expected_human_events)
        baseline = build_matrix_snapshot(baseline_scene or after_scene, expected_human_events)
        previous = build_matrix_snapshot(before_scene, expected_human_events) if before_scene else None
        world_metrics = matrix_score(current, baseline, previous)
        metrics.update({str(key): value for key, value in world_metrics.items()})
    except Exception as error:
        metrics["score_error"] = str(error)
    return metrics


class RunService:
    def __init__(self, db: Session, current_user: User | None = None) -> None:
        self.current_user = current_user
        self.runs = RunRepository(db)
        self.scenes = SceneRepository(db)

    def list_runs(self) -> list[RunRead]:
        if self.current_user is None or self.current_user.role == "admin":
            return [_run_read(run) for run in self.runs.list()]
        return [_run_read(run) for run in self.runs.list_for_user(self.current_user.id)]

    def get_run(self, run_id: str) -> RunRead:
        run = self._require_run(run_id)
        return _run_read(run)

    def create_run(self, request: RunCreate) -> RunCurrentResponse:
        version = self.scenes.get_version(request.scene_version_id)
        if version is None:
            raise NotFoundError(f"Scene version not found: {request.scene_version_id}")
        control_mode = request.control_mode
        visibility_mode = request.visibility_mode
        agent_model = request.agent_model
        config = dict(request.config)
        scheduled_events = expected_events(version.source_json, request.max_steps)
        if self.current_user is not None and self.current_user.role != "admin":
            if control_mode == ControlMode.agent:
                raise InvalidStateError("Agent control is only available to admins")
            if visibility_mode != VisibilityMode.fog_of_war:
                raise InvalidStateError("User runs must use fog_of_war visibility")
            agent_model = None
            config["use_llm"] = False
        status = RunStatus.waiting_for_human.value if control_mode == ControlMode.human else RunStatus.pending.value
        run = Run(
            id=_run_id(),
            owner_user_id=self.current_user.id if self.current_user is not None else None,
            scene_version_id=request.scene_version_id,
            control_mode=control_mode.value,
            visibility_mode=visibility_mode.value,
            status=status,
            current_step=0,
            config={
                "task_id": request.task_id,
                "agent_model": agent_model,
                "max_steps": request.max_steps,
                "seed": request.seed,
                "expected_events": list(scheduled_events),
                **config,
            },
            summary={},
            started_at=datetime.now(timezone.utc),
        )
        saved = self.runs.create(run)
        if request.control_mode in {ControlMode.agent, ControlMode.npc_only}:
            self._try_enqueue(saved)
        return self.current(saved.id)

    def current(self, run_id: str) -> RunCurrentResponse:
        run = self._require_run(run_id)
        version = self.scenes.get_version(run.scene_version_id)
        if version is None:
            raise NotFoundError(f"Scene version not found: {run.scene_version_id}")
        steps = self.runs.steps(run.id)
        selected_actions = [copy.deepcopy(step.selected_action) for step in steps if step.selected_action]
        adapter = GraphWorldAdapter(version.source_json)
        orchestrator = adapter.replay_orchestrator(selected_actions, visibility_mode=run.visibility_mode)
        observation = self._with_memory(
            adapter.observation(orchestrator, visibility_mode=run.visibility_mode),
            steps,
        )
        latest_result = _action_result(steps[-1].action_result) if steps and steps[-1].action_result else None
        return RunCurrentResponse(
            run=_run_read(run),
            observation=observation,
            candidate_actions=observation.candidate_actions,
            latest_action_result=latest_result,
            metrics=self._summary_metrics(run, steps),
        )

    def apply_human_action(self, run_id: str, request: ActionRequest) -> RunCurrentResponse:
        run = self._require_run(run_id)
        if run.control_mode != ControlMode.human.value:
            raise InvalidStateError(f"Run {run_id} is not in human control mode")
        if run.status not in {RunStatus.waiting_for_human.value, RunStatus.running.value}:
            raise InvalidStateError(f"Run {run_id} cannot accept actions while status={run.status}")
        selected = self._candidate_for_current_state(run, request.action_id, request.payload)
        return self._apply_selected_action(run, selected, actor_type="human")

    def apply_human_interaction(self, run_id: str, request: Any) -> RunCurrentResponse:
        """Resolve physical player input before entering canonical actions."""
        run = self._require_run(run_id)
        if run.control_mode != ControlMode.human.value:
            raise InvalidStateError(f"Run {run_id} is not in human control mode")
        if run.status not in {RunStatus.waiting_for_human.value, RunStatus.running.value}:
            raise InvalidStateError(f"Run {run_id} cannot accept interactions while status={run.status}")
        _, orchestrator = self._adapter_and_orchestrator(run)
        payload = request.model_dump(mode="json") if hasattr(request, "model_dump") else dict(request)
        resolved = resolve_interaction(orchestrator.graph.state_for_rules(), CoreInteractionRequest.from_dict(payload))
        if resolved.action is None:
            raise InvalidStateError("; ".join(resolved.failures))
        if payload.get("hit"):
            resolved.action["interaction_hit"] = payload["hit"]
        return self._apply_selected_action(run, resolved.action, actor_type="human")

    def advance_run(self, run_id: str) -> RunCurrentResponse:
        run = self._require_run(run_id)
        if run.control_mode == ControlMode.human.value:
            raise InvalidStateError(f"Run {run_id} is controlled by a human; submit an action instead")
        if run.status in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.canceled.value}:
            return self.current(run.id)
        if run.control_mode == ControlMode.npc_only.value:
            return self._apply_selected_action(run, {}, actor_type="npc_only")
        selected = self._choose_agent_action(run)
        if not selected:
            self._complete_run(run, reason="no legal candidate actions")
            return self.current(run.id)
        return self._apply_selected_action(run, selected, actor_type="agent")

    def run_to_completion(self, run_id: str) -> RunRead:
        run = self._require_run(run_id)
        max_steps = max(1, int((run.config or {}).get("max_steps") or 1))
        while run.status not in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.canceled.value}:
            if run.current_step >= max_steps:
                self._complete_run(run, reason="max_steps reached")
                break
            self.advance_run(run.id)
            run = self._require_run(run_id)
        return _run_read(run)

    def cancel_run(self, run_id: str) -> RunRead:
        run = self._require_run(run_id)
        if run.status not in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.canceled.value}:
            run.status = RunStatus.canceled.value
            run.finished_at = datetime.now(timezone.utc)
            self.runs.commit()
        return _run_read(run)

    def steps(self, run_id: str, *, offset: int = 0, limit: int = 100) -> list[ReplayStepRead]:
        self._require_run(run_id)
        return [_step_read(step) for step in self.runs.steps(run_id, offset=offset, limit=limit)]

    def step(self, run_id: str, step_index: int) -> ReplayStepRead:
        self._require_run(run_id)
        step = self.runs.step(run_id, step_index)
        if step is None:
            raise NotFoundError(f"Run step not found: {run_id} step {step_index}")
        return _step_read(step)

    def replay(self, run_id: str) -> ReplayResponse:
        run = self._require_run(run_id)
        steps = self.runs.steps(run.id)
        return ReplayResponse(run_id=run.id, steps=[_step_read(step) for step in steps], summary=run.summary or {})

    def metrics(self, run_id: str) -> RunMetricsResponse:
        run = self._require_run(run_id)
        steps = self.runs.steps(run.id)
        points: list[MetricPoint] = []
        for step in steps:
            for name, value in (step.metrics or {}).items():
                if isinstance(value, bool):
                    metric_value = 1.0 if value else 0.0
                elif isinstance(value, int | float):
                    metric_value = float(value)
                else:
                    metric_value = None
                points.append(
                    MetricPoint(
                        step_index=step.step_index,
                        metric_name=str(name),
                        metric_value=metric_value,
                        payload={"value": value},
                    )
                )
        if not points:
            points.append(
                MetricPoint(
                    step_index=run.current_step,
                    metric_name="step_count",
                    metric_value=float(run.current_step),
                    payload={},
                )
            )
        return RunMetricsResponse(run_id=run.id, metrics=points, summary=run.summary or {})

    def _require_run(self, run_id: str) -> Run:
        run = self.runs.get(run_id)
        if run is None:
            raise NotFoundError(f"Run not found: {run_id}")
        if self.current_user is not None and self.current_user.role != "admin" and run.owner_user_id != self.current_user.id:
            raise NotFoundError(f"Run not found: {run_id}")
        return run

    def _selected_actions(self, run: Run) -> list[dict[str, Any]]:
        return [copy.deepcopy(step.selected_action) for step in self.runs.steps(run.id) if step.selected_action]

    def _adapter_and_orchestrator(self, run: Run) -> tuple[GraphWorldAdapter, Any]:
        version = self.scenes.get_version(run.scene_version_id)
        if version is None:
            raise NotFoundError(f"Scene version not found: {run.scene_version_id}")
        adapter = GraphWorldAdapter(version.source_json)
        return adapter, adapter.replay_orchestrator(self._selected_actions(run), visibility_mode=run.visibility_mode)

    def _candidate_for_current_state(
        self,
        run: Run,
        selected_action_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        adapter, orchestrator = self._adapter_and_orchestrator(run)
        selected = adapter.candidate_by_id(
            orchestrator,
            visibility_mode=run.visibility_mode,
            selected_action_id=selected_action_id,
        )
        if selected is None:
            raise InvalidStateError(f"Action is not currently available: {selected_action_id}")
        # Candidate identity and action arguments come from the server-side
        # candidate set. Only geometric interaction hints may be supplied by
        # the client (surface/volume hit points and release anchor).
        allowed_payload = {
            key: value
            for key, value in (payload or {}).items()
            if key in {"surface_anchor", "surface_point_cm", "volume_anchor", "volume_point_cm", "release_anchor", "interaction_hit", "destination_room", "target_room"}
        }
        if "interaction_hit" in allowed_payload:
            visible_ids = {
                str(item.get("id") or "")
                for item in (adapter.runtime_observation(orchestrator, visibility_mode=run.visibility_mode).get("nodes") or [])
                if isinstance(item, dict) and item.get("id")
            }
            failures = validate_interaction_hit(
                allowed_payload["interaction_hit"],
                target_id=str(selected.get("target") or ""),
                visible_node_ids=visible_ids,
            )
            if failures:
                raise InvalidStateError("; ".join(failures))
        selected.update(allowed_payload)
        return selected

    def _choose_agent_action(self, run: Run) -> dict[str, Any]:
        adapter, orchestrator = self._adapter_and_orchestrator(run)
        candidates = adapter.candidate_payloads(orchestrator, visibility_mode=run.visibility_mode)
        if not candidates:
            return {}
        config = run.config or {}
        agent_model = str(config.get("agent_model") or "")
        if agent_model and bool(config.get("use_llm", False)):
            raw_observation = adapter.runtime_observation(orchestrator, visibility_mode=run.visibility_mode)
            try:
                selected, answer = llm_choose_action(
                    candidates,
                    raw_observation,
                    agent_model,
                    adapter.source_json,
                    agent_id=adapter.agent_id,
                )
                selected = copy.deepcopy(selected)
                selected["llm_answer"] = answer
                return selected
            except Exception as error:  # pragma: no cover - network/model fallback
                selected = fallback_choose_action(candidates)
                selected = copy.deepcopy(selected)
                selected["llm_error"] = str(error)
                return selected
        return copy.deepcopy(fallback_choose_action(candidates))

    def _apply_selected_action(self, run: Run, selected: dict[str, Any], *, actor_type: str) -> RunCurrentResponse:
        adapter, orchestrator = self._adapter_and_orchestrator(run)
        before_observation = self._with_memory(
            adapter.observation(orchestrator, visibility_mode=run.visibility_mode),
            self.runs.steps(run.id),
        )
        before_scene = orchestrator.graph.to_scene()
        human_events = planned_events_for_step(before_scene, run.current_step)
        if actor_type == "npc_only":
            result = orchestrator.step(robot_actions=[], human_events=human_events, capture_robot_scene=False)
            first_result = {"ok": True, "message": "advanced environment"}
        else:
            result = orchestrator.step(
                robot_actions=[copy.deepcopy(selected)],
                human_events=human_events,
                capture_robot_scene=False,
            )
            robot_results = result.get("robot_actions") or []
            first_result = robot_results[0] if robot_results else {}
        after_scene = orchestrator.graph.to_scene()
        action_result = _action_result(first_result)
        candidate_actions = [item.model_dump(mode="json") for item in before_observation.candidate_actions]
        metrics = _metrics_for_step(
            before_observation,
            candidate_actions,
            action_result,
            after_scene,
            baseline_scene=adapter.source_json,
            before_scene=before_scene,
            expected_human_events=tuple(str(item) for item in (run.config or {}).get("expected_events") or ()),
        )
        step = RunStep(
            run_id=run.id,
            step_index=run.current_step,
            actor_type=actor_type,
            actor_id=str(selected.get("agent") or "robot_01") if selected else "",
            observation=before_observation.model_dump(mode="json"),
            candidate_actions=candidate_actions,
            selected_action=copy.deepcopy(selected),
            action_result=action_result.model_dump(mode="json"),
            world_state_before=copy.deepcopy(before_scene.get("world_state") or {}),
            world_state_after=copy.deepcopy(after_scene.get("world_state") or {}),
            events=_events_since(before_scene, after_scene),
            metrics=metrics,
        )
        self.runs.add_step(step)
        run.current_step += 1
        run.status = RunStatus.waiting_for_human.value if run.control_mode == ControlMode.human.value else RunStatus.running.value
        self._update_summary(run)
        max_steps = int((run.config or {}).get("max_steps") or 0)
        if max_steps and run.current_step >= max_steps:
            self._complete_run(run, reason="max_steps reached")
        else:
            self.runs.commit()
        response = self.current(run.id)
        response.latest_action_result = action_result
        return response

    def _with_memory(self, observation: Observation, steps: list[RunStep]) -> Observation:
        if observation.visibility_mode == "full":
            return observation
        visible_ids = {str(item.get("id") or "") for item in observation.visible_nodes if item.get("id")}
        seen_nodes: dict[str, dict[str, Any]] = {}
        for step in steps:
            for node in (step.observation or {}).get("visible_nodes") or []:
                node_id = str(node.get("id") or "")
                if node_id and node_id not in visible_ids:
                    seen_nodes[node_id] = copy.deepcopy(node)
        status_by_node = dict(observation.observation_status_by_node)
        last_seen_by_node = dict(observation.last_seen_step_by_node)
        for node_id, node in seen_nodes.items():
            node["observation_status"] = status_by_node.get(node_id, "stale")
            if node_id in last_seen_by_node:
                node["last_seen_step"] = last_seen_by_node[node_id]
        unknown_rooms = [
            room_id
            for room_id, status in sorted(observation.observation_status_by_room.items())
            if status == "unknown"
        ]
        return observation.model_copy(
            update={
                "memory_nodes": [seen_nodes[node_id] for node_id in sorted(seen_nodes)],
                "unknown_rooms": unknown_rooms,
                "observation_status_by_node": status_by_node,
                "last_seen_step_by_node": last_seen_by_node,
            }
        )

    def _summary_metrics(self, run: Run, steps: list[RunStep]) -> dict[str, Any]:
        ok_count = sum(1 for step in steps if (step.action_result or {}).get("ok") is True)
        return {
            "step_count": len(steps),
            "ok_action_count": ok_count,
            "failed_action_count": len(steps) - ok_count,
            **(run.summary or {}),
        }

    def _update_summary(self, run: Run) -> None:
        steps = self.runs.steps(run.id)
        ok_count = sum(1 for step in steps if (step.action_result or {}).get("ok") is True)
        latest_metrics = copy.deepcopy(steps[-1].metrics) if steps else {}
        run.summary = {
            **(run.summary or {}),
            **latest_metrics,
            "step_count": len(steps),
            "ok_action_count": ok_count,
            "failed_action_count": len(steps) - ok_count,
            "last_action_id": action_id(steps[-1].selected_action) if steps and steps[-1].selected_action else "",
        }

    def _complete_run(self, run: Run, *, reason: str) -> None:
        self._update_summary(run)
        run.summary = {**(run.summary or {}), "completion_reason": reason}
        run.status = RunStatus.completed.value
        run.finished_at = datetime.now(timezone.utc)
        self.runs.commit()

    def _try_enqueue(self, run: Run) -> None:
        try:
            from backend.app.workers.queue import enqueue_run

            job = enqueue_run(run.id)
            run.summary = {**(run.summary or {}), "queue_job_id": job.id}
            self.runs.commit()
        except Exception as error:
            run.summary = {**(run.summary or {}), "queue_error": str(error)}
            self.runs.commit()
