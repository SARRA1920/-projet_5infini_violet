"""fusion audit_log, actuariat et password_resets

Revision ID: 82c206b49bc3
Revises: 2e4a809d8117, 7b1e4a2c9d10, a91c0e4b7d12
Create Date: 2026-11-13 11:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82c206b49bc3'
down_revision: Union[str, Sequence[str], None] = ('2e4a809d8117', '7b1e4a2c9d10', 'a91c0e4b7d12')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
