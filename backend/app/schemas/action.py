from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CandidateAction(BaseModel):
    action_id: str
    action_type: str
    actor_id: str = ""
    target_id: str = ""
    object_id: str = ""
    reason: str = ""
    legal: bool = True
    preview: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    action_contract: dict[str, Any] = Field(default_factory=dict)


class ActionRequest(BaseModel):
    action_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class InteractionRequest(BaseModel):
    actor_id: str = "robot_01"
    input: str = "interact_primary"
    target_id: str = ""
    distance_m: float | None = None
    hit: dict[str, Any] = Field(default_factory=dict)
    hand: str = "right"


class ActionResult(BaseModel):
    ok: bool
    message: str = ""
    failures: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
