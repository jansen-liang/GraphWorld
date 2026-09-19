from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.auth import get_current_user, require_admin
from backend.app.core.errors import NotFoundError
from backend.app.db.models import User
from backend.app.db.session import get_db
from backend.app.schemas.graph import SceneGraphResponse
from backend.app.schemas.scene import (
    SceneImportRequest,
    SceneLayoutRequest,
    SceneLayoutValidation,
    ScenePublishRequest,
    SceneRead,
    SceneVersionRead,
)
from backend.app.services.scene_service import SceneService

router = APIRouter()


def get_scene_service(db: Session = Depends(get_db)) -> Iterator[SceneService]:
    yield SceneService(db)


@router.get("/scenes", response_model=list[SceneRead])
def list_scenes(
    _: User = Depends(get_current_user),
    service: SceneService = Depends(get_scene_service),
) -> list[SceneRead]:
    return service.list_scenes()


@router.post("/scenes/import", response_model=SceneVersionRead, status_code=201)
def import_scene(
    request: SceneImportRequest,
    _: User = Depends(require_admin),
    service: SceneService = Depends(get_scene_service),
) -> SceneVersionRead:
    return service.import_scene(request)


@router.get("/scenes/{scene_id}", response_model=SceneRead)
def get_scene(
    scene_id: str,
    _: User = Depends(get_current_user),
    service: SceneService = Depends(get_scene_service),
) -> SceneRead:
    try:
        return service.get_scene(scene_id)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/scenes/{scene_id}/versions", response_model=list[SceneVersionRead])
def list_scene_versions(
    scene_id: str,
    _: User = Depends(get_current_user),
    service: SceneService = Depends(get_scene_service),
) -> list[SceneVersionRead]:
    try:
        return service.list_versions(scene_id)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/scene-versions/{scene_version_id}/graph", response_model=SceneGraphResponse)
def get_scene_graph(
    scene_version_id: str,
    _: User = Depends(get_current_user),
    service: SceneService = Depends(get_scene_service),
) -> SceneGraphResponse:
    try:
        return service.get_graph(scene_version_id)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/scene-versions/{scene_version_id}/layout/validate", response_model=SceneLayoutValidation)
def validate_scene_layout(
    scene_version_id: str,
    request: SceneLayoutRequest,
    _: User = Depends(require_admin),
    service: SceneService = Depends(get_scene_service),
) -> SceneLayoutValidation:
    try:
        return service.validate_layout(scene_version_id, request.source_json)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/scene-versions/{scene_version_id}/layout/publish", response_model=SceneVersionRead, status_code=201)
def publish_scene_layout(
    scene_version_id: str,
    request: ScenePublishRequest,
    _: User = Depends(require_admin),
    service: SceneService = Depends(get_scene_service),
) -> SceneVersionRead:
    try:
        return service.publish_layout(scene_version_id, request)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
