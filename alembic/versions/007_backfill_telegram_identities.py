"""backfill missing telegram identities and ensure all users have at least one identity row

Users created via /auth/telegram after migration 005 may lack a user_identities row
because the old endpoint only wrote to users.telegram_id. This migration back-fills them.

Revision ID: 007
Revises: 006
Create Date: 2026-04-10

"""
from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO user_identities (user_id, provider, external_id)
        SELECT u.id, 'telegram', u.telegram_id::text
        FROM users u
        WHERE u.telegram_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM user_identities ui
              WHERE ui.user_id = u.id
                AND ui.provider = 'telegram'
                AND ui.external_id = u.telegram_id::text
          )
        """
    )


def downgrade() -> None:
    pass
