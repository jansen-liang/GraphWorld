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
    SceneLayoutGenerated,
    SceneLayoutGenerateRequest,
    SceneLayoutRequest,
    SceneLayoutValidation,
    ScenePublishRequest,
    SceneRead,
    SceneVersionRead,
    SimulationDispatchRequest,
    SimulationSessionResponse,
    SimulationStartRequest,
)
from backend.app.services.scene_service import SceneService
from backend.app.services.simulation_service import simulation_world_service

router = APIRouter()


@router.post("/scene-simulation/start", response_model=SimulationSessionResponse)
def start_scene_simulation(
    request: SimulationStartRequest,
    _: User = Depends(require_admin),
) -> SimulationSessionResponse:
    return simulation_world_service.start(request)


@router.post("/scene-simulation/dispatch", response_model=SimulationSessionResponse)
def dispatch_scene_simulation(
    request: SimulationDispatchRequest,
    _: User = Depends(require_admin),
) -> SimulationSessionResponse:
    try:
        return simulation_world_service.dispatch(request)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/scene-simulation/{simulation_id}", status_code=204)
def stop_scene_simulation(
    simulation_id: str,
    _: User = Depends(require_admin),
) -> None:
    simulation_world_service.stop(simulation_id)


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


@router.post("/scene-versions/{scene_version_id}/layout/generate", response_model=SceneLayoutGenerated)
def generate_scene_layout(
    scene_version_id: str,
    request: SceneLayoutGenerateRequest,
    _: User = Depends(require_admin),
    service: SceneService = Depends(get_scene_service),
) -> SceneLayoutGenerated:
    """Materialize composite topology and generate a deterministic layout."""
    try:
        return service.generate_layout(scene_version_id, request)
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
