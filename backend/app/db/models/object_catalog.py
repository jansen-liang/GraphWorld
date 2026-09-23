from __future__ import annotations

from sqlalchemy import Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.models.base import Base, TimestampMixin
from backend.app.db.models.types import JSONBType


class ObjectCatalog(TimestampMixin, Base):
    """Versioned-independent physical and semantic specification for objects."""

    __tablename__ = "object_catalog"

    semantic_type: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_cn: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="object", nullable=False)
    width_cm: Mapped[float] = mapped_column(Float, nullable=False)
    depth_cm: Mapped[float] = mapped_column(Float, nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    capabilities: Mapped[list] = mapped_column(JSONBType, default=list, nullable=False)
    state_schema: Mapped[dict] = mapped_column(JSONBType, default=dict, nullable=False)
    default_states: Mapped[dict] = mapped_column(JSONBType, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
