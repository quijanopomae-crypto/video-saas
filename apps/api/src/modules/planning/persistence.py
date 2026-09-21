from __future__ import annotations

from typing import Any

from sqlalchemy import text

from ...core.db import get_engine


def save_planning_flow(owner_id: str, flow: dict[str, Any]) -> dict[str, Any]:
    owner = owner_id.strip()
    if not owner:
        raise ValueError("owner_id is required")
    project_id = str(flow["project_bible"]["project_id"])
    statement = text(
        """
        INSERT INTO planning_projects (owner_id, project_id, flow_json)
        VALUES (:owner_id, :project_id, CAST(:flow_json AS jsonb))
        ON CONFLICT (owner_id, project_id)
        DO UPDATE SET flow_json = EXCLUDED.flow_json
        """
    )
    import json
    with get_engine().begin() as connection:
        connection.execute(statement, {"owner_id": owner, "project_id": project_id, "flow_json": json.dumps(flow)})
    return flow


def load_planning_flow(owner_id: str, project_id: str) -> dict[str, Any] | None:
    owner = owner_id.strip()
    if not owner:
        raise ValueError("owner_id is required")
    statement = text(
        """
        SELECT flow_json
        FROM planning_projects
        WHERE owner_id = :owner_id AND project_id = :project_id
        """
    )
    with get_engine().connect() as connection:
        row = connection.execute(statement, {"owner_id": owner, "project_id": project_id}).first()
    if row is None:
        return None
    return dict(row[0])
