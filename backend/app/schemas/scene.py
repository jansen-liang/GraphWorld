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


class SceneLayoutValidation(BaseModel):
    valid: bool
    issues: list[str] = Field(default_factory=list)


class ScenePublishRequest(BaseModel):
    source_json: dict[str, Any]
    description: str = "Published from the 2D scene builder."
