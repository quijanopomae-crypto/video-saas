from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from ...core.auth import Principal, get_current_principal
from . import ProjectRequest, run_product_flow
from .persistence import load_planning_flow, save_planning_flow

router = APIRouter(tags=["planning"])


class PlanningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    idea: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
    duration_sec: Annotated[int, Field(strict=True, ge=5, le=600)]
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    audience: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] = "general"
    tone: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] = "clear"
    language: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)] = "es"


def _canonical_flow(payload: PlanningRequest) -> dict:
    try:
        request = ProjectRequest.from_dict(payload.model_dump())
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return run_product_flow(request).to_dict()


def _authorized_owner(owner_id: str, principal: Principal) -> str:
    owner = owner_id.strip()
    if not owner:
        raise HTTPException(status_code=422, detail="owner_id is required")
    if owner != principal.user_id:
        raise HTTPException(status_code=403, detail="owner access denied")
    return principal.user_id


@router.post("/planning")
def planning(payload: PlanningRequest) -> dict:
    return _canonical_flow(payload)


@router.post("/owners/{owner_id}/planning")
def persist_planning(
    owner_id: str,
    payload: PlanningRequest,
    principal: Principal = Depends(get_current_principal),
) -> dict:
    effective_owner = _authorized_owner(owner_id, principal)
    flow = _canonical_flow(payload)
    return save_planning_flow(effective_owner, flow)


@router.get("/owners/{owner_id}/planning/{project_id}")
def read_planning(
    owner_id: str,
    project_id: str,
    principal: Principal = Depends(get_current_principal),
) -> dict:
    effective_owner = _authorized_owner(owner_id, principal)
    flow = load_planning_flow(effective_owner, project_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="planning project not found")
    return flow
