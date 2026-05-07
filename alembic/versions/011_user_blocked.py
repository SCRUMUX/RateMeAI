"""add admin block fields to users

Revision ID: 011
Revises: 010
Create Date: 2026-05-07

Adds three nullable columns to ``users`` so the admin panel can
soft-block accounts:

- ``blocked_at`` (TIMESTAMPTZ) — when the block was applied; NULL
  means the user is active. ``get_auth_user`` and the web/OAuth
  auth handlers fail with HTTP 403 ``{code: "account_blocked"}``
  whenever this is non-NULL.
- ``blocked_reason`` (TEXT) — human-readable cause shown to the
  blocked user on the in-app overlay (and to admins in the
  Users tab drawer).
- ``blocked_by`` (UUID) — the admin who pressed the button.
  Audit-only; not a foreign key on purpose, so deleting an admin
  account doesn't cascade-clear historical block records.

All three are nullable. Existing rows default to NULL — no
behaviour change for previously-registered users.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("blocked_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("blocked_by", UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "blocked_by")
    op.drop_column("users", "blocked_reason")
    op.drop_column("users", "blocked_at")
