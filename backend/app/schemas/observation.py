from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.action import CandidateAction


class Observation(BaseModel):
    actor_id: str
    step_index: int
    visibility_mode: str
    visible_rooms: list[str] = Field(default_factory=list)
    visible_nodes: list[dict[str, Any]] = Field(default_factory=list)
    visible_edges: list[dict[str, Any]] = Field(default_factory=list)
    memory_nodes: list[dict[str, Any]] = Field(default_factory=list)
    unknown_rooms: list[str] = Field(default_factory=list)
    confidence_by_room: dict[str, float] = Field(default_factory=dict)
    observation_status_by_node: dict[str, str] = Field(default_factory=dict)
    last_seen_step_by_node: dict[str, int] = Field(default_factory=dict)
    observation_status_by_room: dict[str, str] = Field(default_factory=dict)
    candidate_actions: list[CandidateAction] = Field(default_factory=list)
    camera: dict[str, Any] = Field(default_factory=dict)
