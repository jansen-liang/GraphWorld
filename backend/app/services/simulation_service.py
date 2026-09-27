"""Stateless scene simulation used by editor previews."""

from __future__ import annotations

import copy
from typing import Any

from backend.app.schemas.scene import SceneInteractionRequest, SceneInteractionResponse, SceneTickRequest
from backend.core.composition import materialize_compositions
from backend.core.interaction import InteractionRequest, resolve_interaction
from backend.core.mutation import MutationPipeline
from backend.core.rules import advance_time
from backend.core.world_graph import WorldGraph


class SimulationService:
    def interact(self, request: SceneInteractionRequest) -> SceneInteractionResponse:
        graph = WorldGraph(materialize_compositions(copy.deepcopy(request.source_json)))
        resolved = resolve_interaction(
            graph.state_for_rules(),
            InteractionRequest(
                actor_id=request.actor_id,
                input=request.input,
                target_id=request.target_id,
                distance_m=request.distance_m,
                hit=copy.deepcopy(request.hit),
                hand=request.hand,
            ),
        )
        if resolved.action is None:
            return SceneInteractionResponse(
                applied=False,
                failures=list(resolved.failures),
                source_json=graph.to_scene(),
            )
        mutation = MutationPipeline(graph).apply_action(
            resolved.action,
            step=int(graph.world_state.get("step") or 0),
        )
        return SceneInteractionResponse(
            applied=mutation.ok,
            action=copy.deepcopy(resolved.action),
            failures=list(mutation.failures),
            delta=mutation.delta.to_dict(),
            source_json=graph.to_scene(),
        )

    def tick(self, request: SceneTickRequest) -> SceneInteractionResponse:
        graph = WorldGraph(materialize_compositions(copy.deepcopy(request.source_json)))
        pipeline = MutationPipeline(graph)
        delta = pipeline.run_system(
            lambda state: advance_time(state, request.elapsed_steps)
        )
        return SceneInteractionResponse(
            applied=True,
            delta=delta.to_dict(),
            source_json=graph.to_scene(),
        )


__all__ = ["SimulationService"]
