"""battery state and history of a device

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('devices') as b:
        b.add_column(sa.Column('batt_state', sa.String(), nullable=True))
        b.add_column(sa.Column('batt_hist', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('devices') as b:
        b.drop_column('batt_hist')
        b.drop_column('batt_state')
