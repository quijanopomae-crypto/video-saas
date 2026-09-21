"""Persist owner-scoped canonical planning outputs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_planning_projects"
down_revision = "0001_infra_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planning_projects",
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("flow_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("owner_id", "project_id"),
    )


def downgrade() -> None:
    op.drop_table("planning_projects")
