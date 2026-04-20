"""add deletion_log table

Revision ID: 010
Revises: 009
Create Date: 2026-04-20

Audit trail for the GDPR Art. 17 / 152-ФЗ ст. 14 "right to erasure"
endpoint (DELETE /api/v1/users/me). One row per successful deletion,
storing only *non-PII* evidence:

- opaque ``user_id_hash`` (SHA-256 of UUID, not the raw UUID — the row
  must survive past the moment the user is gone and still not be able
  to re-identify them);
- number of artefacts physically removed (tasks, share-cards, generated
  images, consent rows, perception records);
- hashed source marker (api / bot / admin) and IP hash;
- ``deleted_at`` timestamp.

Used by privacy ops to prove to a regulator that an erasure request
was actually honoured, without re-introducing PII.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deletion_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id_hash", sa.String(64), nullable=False, index=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="api"),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("user_agent_hash", sa.String(64), nullable=True),
        sa.Column("tasks_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generated_files_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("share_cards_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consents_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("perception_records_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("identities_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("deletion_log")
