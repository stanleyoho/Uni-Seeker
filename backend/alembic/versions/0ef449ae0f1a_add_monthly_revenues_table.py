"""add monthly_revenues table

Revision ID: 0ef449ae0f1a
Revises: 
Create Date: 2026-04-23 21:51:25.230523
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0ef449ae0f1a'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('monthly_revenues',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('symbol', sa.String(length=20), nullable=False),
    sa.Column('period', sa.String(length=10), nullable=False),
    sa.Column('revenue', sa.Float(), nullable=False),
    sa.Column('mom_growth', sa.Float(), nullable=True),
    sa.Column('yoy_growth', sa.Float(), nullable=True),
    sa.Column('industry', sa.String(length=50), nullable=False),
    sa.Column('currency', sa.String(length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_monthly_revenues_period'), 'monthly_revenues', ['period'], unique=False)
    op.create_index(op.f('ix_monthly_revenues_symbol'), 'monthly_revenues', ['symbol'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_monthly_revenues_symbol'), table_name='monthly_revenues')
    op.drop_index(op.f('ix_monthly_revenues_period'), table_name='monthly_revenues')
    op.drop_table('monthly_revenues')
