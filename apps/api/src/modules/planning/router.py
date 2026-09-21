from typing import Any

from fastapi import APIRouter, HTTPException

from . import ProjectRequest, run_product_flow
from .persistence import load_planning_flow, save_planning_flow

router = APIRouter(tags=["planning"])


def _canonical_flow(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        request = ProjectRequest.from_dict(payload)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return run_product_flow(request).to_dict()


@router.post("/planning")
def planning(payload: dict[str, Any]) -> dict[str, Any]:
    return _canonical_flow(payload)


@router.post("/owners/{owner_id}/planning")
def persist_planning(owner_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not owner_id.strip():
        raise HTTPException(status_code=422, detail="owner_id is required")
    flow = _canonical_flow(payload)
    return save_planning_flow(owner_id, flow)


@router.get("/owners/{owner_id}/planning/{project_id}")
def read_planning(owner_id: str, project_id: str) -> dict[str, Any]:
    if not owner_id.strip():
        raise HTTPException(status_code=422, detail="owner_id is required")
    flow = load_planning_flow(owner_id, project_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="planning project not found")
    return flow
