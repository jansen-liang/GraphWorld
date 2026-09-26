from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.api.auth import get_current_user
from backend.app.core.errors import InvalidStateError, NotFoundError
from backend.app.db.models import User
from backend.app.db.session import get_db
from backend.app.schemas.action import ActionRequest, InteractionRequest
from backend.app.schemas.metrics import RunMetricsResponse
from backend.app.schemas.replay import ReplayResponse, ReplayStepRead
from backend.app.schemas.run import RunCreate, RunCurrentResponse, RunRead
from backend.app.services.run_service import RunService

router = APIRouter()


def get_run_service(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Iterator[RunService]:
    yield RunService(db, user)


@router.post("/runs", response_model=RunCurrentResponse, status_code=201)
def create_run(request: RunCreate, service: RunService = Depends(get_run_service)) -> RunCurrentResponse:
    try:
        return service.create_run(request)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidStateError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.get("/runs", response_model=list[RunRead])
def list_runs(service: RunService = Depends(get_run_service)) -> list[RunRead]:
    return service.list_runs()


@router.get("/runs/{run_id}", response_model=RunRead)
def get_run(run_id: str, service: RunService = Depends(get_run_service)) -> RunRead:
    try:
        return service.get_run(run_id)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/runs/{run_id}/current", response_model=RunCurrentResponse)
def current_run(run_id: str, service: RunService = Depends(get_run_service)) -> RunCurrentResponse:
    try:
        return service.current(run_id)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/runs/{run_id}/actions", response_model=RunCurrentResponse)
def apply_human_action(
    run_id: str,
    request: ActionRequest,
    service: RunService = Depends(get_run_service),
) -> RunCurrentResponse:
    try:
        return service.apply_human_action(run_id, request)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/runs/{run_id}/interactions", response_model=RunCurrentResponse)
def apply_human_interaction(
    run_id: str,
    request: InteractionRequest,
    service: RunService = Depends(get_run_service),
) -> RunCurrentResponse:
    try:
        return service.apply_human_interaction(run_id, request)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/runs/{run_id}/advance", response_model=RunCurrentResponse)
def advance_run(run_id: str, service: RunService = Depends(get_run_service)) -> RunCurrentResponse:
    try:
        return service.advance_run(run_id)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/runs/{run_id}/cancel", response_model=RunRead)
def cancel_run(run_id: str, service: RunService = Depends(get_run_service)) -> RunRead:
    try:
        return service.cancel_run(run_id)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/runs/{run_id}/steps", response_model=list[ReplayStepRead])
def list_run_steps(
    run_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: RunService = Depends(get_run_service),
) -> list[ReplayStepRead]:
    try:
        return service.steps(run_id, offset=offset, limit=limit)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/runs/{run_id}/steps/{step_index}", response_model=ReplayStepRead)
def get_run_step(
    run_id: str,
    step_index: int,
    service: RunService = Depends(get_run_service),
) -> ReplayStepRead:
    try:
        return service.step(run_id, step_index)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/runs/{run_id}/replay", response_model=ReplayResponse)
def get_replay(run_id: str, service: RunService = Depends(get_run_service)) -> ReplayResponse:
    try:
        return service.replay(run_id)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/runs/{run_id}/metrics", response_model=RunMetricsResponse)
def get_metrics(run_id: str, service: RunService = Depends(get_run_service)) -> RunMetricsResponse:
    try:
        return service.metrics(run_id)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
