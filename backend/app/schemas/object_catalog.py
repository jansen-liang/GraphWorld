from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ObjectCatalogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    semantic_type: str
    name: str
    name_cn: str = ""
    category: str = "object"
    width_cm: float
    depth_cm: float
    height_cm: float
    capabilities: list[str] = Field(default_factory=list)
    state_schema: dict[str, Any] = Field(default_factory=dict)
    default_states: dict[str, Any] = Field(default_factory=dict)
