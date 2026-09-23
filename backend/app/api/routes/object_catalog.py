from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.auth import get_current_user
from backend.app.db.models import ObjectCatalog, User
from backend.app.db.session import get_db
from backend.app.schemas.object_catalog import ObjectCatalogRead

router = APIRouter()


@router.get("/object-catalog", response_model=list[ObjectCatalogRead])
def list_object_catalog(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ObjectCatalogRead]:
    entries = db.scalars(select(ObjectCatalog).where(ObjectCatalog.is_active.is_(True)).order_by(ObjectCatalog.semantic_type)).all()
    return [ObjectCatalogRead.model_validate(entry, from_attributes=True) for entry in entries]
