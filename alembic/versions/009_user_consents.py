"""add user_consents table and make tasks.input_image_path nullable

Revision ID: 009
Revises: 008
Create Date: 2026-04-20

Adds the privacy/compliance layer:
- `user_consents` table stores an audit trail of granted/revoked consents
  (one row per grant/revoke event, not "current state"). Current state is
  derived by selecting the latest row per (user_id, kind) with
  `revoked_at IS NULL`.
- `tasks.input_image_path` becomes nullable so new tasks can record that the
  original image was never persisted (embedding-only flow).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_consents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("version", sa.String(16), nullable=False, server_default="1"),
        sa.Column("source", sa.String(32), nullable=False, server_default="web"),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("user_agent_hash", sa.String(64), nullable=True),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_user_consents_user_kind",
        "user_consents",
        ["user_id", "kind"],
    )

    op.alter_column(
        "tasks",
        "input_image_path",
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    op.drop_index("ix_user_consents_user_kind", table_name="user_consents")
    op.drop_table("user_consents")
