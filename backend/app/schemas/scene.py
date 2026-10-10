from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SceneRead(BaseModel):
    id: str
    name: str
    domain: str = ""
    description: str = ""
    created_at: datetime | None = None


class SceneVersionRead(BaseModel):
    id: str
    scene_id: str
    version: int
    graph_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class SceneImportRequest(BaseModel):
    scene_id: str | None = None
    source_json: dict[str, Any]
    description: str = ""


class SceneLayoutRequest(BaseModel):
    source_json: dict[str, Any]


class SceneLayoutGenerateRequest(BaseModel):
    source_json: dict[str, Any] | None = None
    regenerate: bool = True
    materialize_composition: bool = True


class SceneLayoutGenerated(BaseModel):
    source_json: dict[str, Any]
    valid: bool
    issues: list[str] = Field(default_factory=list)
    generated_room_count: int = 0
    generated_object_count: int = 0
    materialized_component_count: int = 0


class SceneLayoutValidation(BaseModel):
    valid: bool
    issues: list[str] = Field(default_factory=list)


class SimulationStartRequest(BaseModel):
    source_json: dict[str, Any]
    actor_id: str = ""


class SimulationDispatchRequest(BaseModel):
    simulation_id: str
    input: str = "interact_primary"
    actor_id: str = ""
    target_id: str = ""
    direction: str = ""
    # Rapier is the client-side authority for continuous character motion.
    # Movement samples carry the resulting world position; the backend only
    # reconciles semantic room/transport relationships.
    position: dict[str, float] | None = None
    physics: dict[str, Any] = Field(default_factory=dict)
    elapsed_seconds: float = Field(default=0.1, ge=0.0, le=1.0)
    distance_m: float | None = None
    hit: dict[str, Any] = Field(default_factory=dict)
    hand: str = "right"
    elapsed_steps: int = Field(default=1, ge=1, le=60)
    event: dict[str, Any] | None = None


class SimulationSessionResponse(BaseModel):
    simulation_id: str
    applied: bool = True
    action: dict[str, Any] | None = None
    failures: list[str] = Field(default_factory=list)
    delta: dict[str, Any] = Field(default_factory=dict)
    snapshot: dict[str, Any]


class ScenePublishRequest(BaseModel):
    source_json: dict[str, Any]
    description: str = "Published from the 2D scene builder."
