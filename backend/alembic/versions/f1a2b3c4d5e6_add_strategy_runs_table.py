"""add strategy_runs table

Revision ID: f1a2b3c4d5e6
Revises: e548a6437867
Create Date: 2026-11-22 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e548a6437867'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'strategy_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('strategy_key', sa.String(length=30), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('window_start', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('day_index', sa.Integer(), nullable=False),
        sa.Column('cash', sa.Float(), nullable=False),
        sa.Column('positions', sa.JSON(), nullable=False),
        sa.Column('position_opened_day', sa.JSON(), nullable=False),
        sa.Column('equity_curve', sa.JSON(), nullable=False),
        sa.Column('violations', sa.JSON(), nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('return_pct', sa.Float(), nullable=True),
        sa.Column('max_drawdown_pct', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_strategy_runs_user_id'), 'strategy_runs', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_strategy_runs_user_id'), table_name='strategy_runs')
    op.drop_table('strategy_runs')
