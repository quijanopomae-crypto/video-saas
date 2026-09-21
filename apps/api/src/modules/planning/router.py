from typing import Any

from fastapi import APIRouter, HTTPException

from . import ProjectRequest, run_product_flow

router = APIRouter(tags=["planning"])


@router.post("/planning")
def planning(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        request = ProjectRequest.from_dict(payload)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return run_product_flow(request).to_dict()
