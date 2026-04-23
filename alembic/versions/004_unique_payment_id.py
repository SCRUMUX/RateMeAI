"""add UNIQUE constraint on credit_transactions.payment_id

Revision ID: 004
Revises: 003
Create Date: 2026-04-04

"""

from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_credit_tx_payment_id",
        "credit_transactions",
        ["payment_id"],
        unique=True,
        postgresql_where="payment_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_credit_tx_payment_id", table_name="credit_transactions")
