"""fusion realized_pnl et stop_loss_take_profit

Revision ID: ed76a0d9c67b
Revises: 8ef40e212f58, d0fe5f500c7f
Create Date: 2026-11-05 10:43:08.660432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed76a0d9c67b'
down_revision: Union[str, Sequence[str], None] = ('8ef40e212f58', 'd0fe5f500c7f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
