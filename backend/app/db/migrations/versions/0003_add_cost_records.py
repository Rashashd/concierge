"""Add cost_records table for per-tenant LLM token attribution.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cost_records",
        sa.Column(
            "id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cost_records_tenant_id", "cost_records", ["tenant_id"])
    op.create_index("ix_cost_records_recorded_at", "cost_records", ["recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_cost_records_recorded_at", table_name="cost_records")
    op.drop_index("ix_cost_records_tenant_id", table_name="cost_records")
    op.drop_table("cost_records")
