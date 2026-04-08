"""add user_perception_records table for best perception scores tracking

Revision ID: 006
Revises: 005
Create Date: 2026-04-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_perception_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("style", sa.String(100), nullable=False),
        sa.Column("warmth", sa.Float(), nullable=False, server_default="0"),
        sa.Column("presence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("appeal", sa.Float(), nullable=False, server_default="0"),
        sa.Column("authenticity", sa.Float(), nullable=False, server_default="9"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "mode", "style", name="uq_perception_user_mode_style"),
    )


def downgrade() -> None:
    op.drop_table("user_perception_records")
