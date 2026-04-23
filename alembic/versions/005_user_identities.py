"""add user_identities table and migrate existing telegram_id data

Revision ID: 005
Revises: 004
Create Date: 2026-04-07

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("profile_data", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "provider", "external_id", name="uq_identity_provider_external"
        ),
    )

    # Migrate existing telegram users into the new identity table
    op.execute(
        """
        INSERT INTO user_identities (user_id, provider, external_id)
        SELECT id, 'telegram', telegram_id::text
        FROM users
        WHERE telegram_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_table("user_identities")
