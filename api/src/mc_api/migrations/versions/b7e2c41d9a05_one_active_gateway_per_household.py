"""one active gateway per household (removed ones may remain)

Revision ID: b7e2c41d9a05
Revises: a24a6c83f64a
Create Date: 2026-09-29 16:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
import mc_api.db.types

revision = 'b7e2c41d9a05'
down_revision = 'a24a6c83f64a'
branch_labels = None
depends_on = None

_ACTIVE = sa.text("status <> 'removed'")


def _gateways_without_unique() -> sa.Table:
    """`gateways` as in a24a6c83f64a, minus its (unnamed) unique constraint."""
    dt = mc_api.db.types.UTCDateTime(timezone=True)
    return sa.Table(
        "gateways", sa.MetaData(),
        sa.Column("id", sa.String(24), primary_key=True),
        sa.Column("household_id", sa.String(26),
                  sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("connected_at", dt), sa.Column("disconnected_at", dt),
        sa.Column("last_outage_s", sa.Integer(), nullable=False),
        sa.Column("last_state", sa.JSON()), sa.Column("last_state_at", dt),
        sa.Column("lan_host_override", sa.String(255)), sa.Column("version", sa.String(32)),
        sa.Column("adapters", sa.JSON()),
        sa.Column("snapshot_rev_applied", sa.Integer(), nullable=False),
        sa.Column("keys_rev_applied", sa.Integer(), nullable=False),
        sa.Column("last_up_seq", sa.Integer(), nullable=False),
        sa.Column("created_at", dt, nullable=False),
    )


def _drop_unique() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("gateways_household_id_key", "gateways", type_="unique")
    else:  # SQLite can't drop constraints: rebuild the table without it
        with op.batch_alter_table("gateways", copy_from=_gateways_without_unique(),
                                  recreate="always"):
            pass


def upgrade() -> None:
    _drop_unique()
    op.create_index("uq_gateways_household_active", "gateways", ["household_id"], unique=True,
                    postgresql_where=_ACTIVE, sqlite_where=_ACTIVE)


def downgrade() -> None:
    op.drop_index("uq_gateways_household_active", table_name="gateways")
    op.execute("DELETE FROM gateways WHERE status = 'removed'")
    with op.batch_alter_table("gateways") as batch_op:
        batch_op.create_unique_constraint("gateways_household_id_key", ["household_id"])
