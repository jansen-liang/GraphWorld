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


class SceneInteractionRequest(BaseModel):
    source_json: dict[str, Any]
    actor_id: str = "robot_01"
    input: str = "interact_primary"
    target_id: str = ""
    distance_m: float | None = None
    hit: dict[str, Any] = Field(default_factory=dict)
    hand: str = "right"


class SceneInteractionResponse(BaseModel):
    applied: bool
    action: dict[str, Any] | None = None
    failures: list[str] = Field(default_factory=list)
    delta: dict[str, Any] = Field(default_factory=dict)
    source_json: dict[str, Any]


class SceneTickRequest(BaseModel):
    source_json: dict[str, Any]
    elapsed_steps: int = Field(default=1, ge=1, le=60)


class ScenePublishRequest(BaseModel):
    source_json: dict[str, Any]
    description: str = "Published from the 2D scene builder."
