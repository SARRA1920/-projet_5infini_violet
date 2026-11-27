"""add ai_runs table

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-11-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ai_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('window_start', sa.Date(), nullable=False),
        sa.Column('shock_pct', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('day_index', sa.Integer(), nullable=False),
        sa.Column('cash', sa.Float(), nullable=False),
        sa.Column('positions', sa.JSON(), nullable=False),
        sa.Column('equity_curve', sa.JSON(), nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('return_pct', sa.Float(), nullable=True),
        sa.Column('max_drawdown_pct', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_runs_user_id'), 'ai_runs', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_ai_runs_user_id'), table_name='ai_runs')
    op.drop_table('ai_runs')
