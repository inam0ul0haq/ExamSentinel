"""make teachers.department_id nullable

Revision ID: 0ef080486833
Revises: 7fd62e721315
Create Date: 2026-05-03 23:47:27.478804

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0ef080486833'
down_revision = '7fd62e721315'
branch_labels = None
depends_on = None


def upgrade():
    # ``batch_alter_table`` is required for SQLite (the dev fallback)
    # because SQLite does not support a direct ``ALTER COLUMN ... DROP
    # NOT NULL``; alembic emulates it by recreating the table inside
    # the batch block. On PostgreSQL the batch wrapper compiles down to
    # a single native ``ALTER COLUMN`` statement, so the same migration
    # works against both backends without branching.
    with op.batch_alter_table('teachers', schema=None) as batch_op:
        batch_op.alter_column(
            'department_id',
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade():
    # Reversing the column requires the table to contain no NULL values
    # in ``department_id``; if any teacher rows have been registered
    # without a department after this migration ran, the downgrade will
    # fail until those rows are backfilled or removed. That is the
    # intended safety check — silently coercing nulls to a default
    # department would lose information.
    with op.batch_alter_table('teachers', schema=None) as batch_op:
        batch_op.alter_column(
            'department_id',
            existing_type=sa.Integer(),
            nullable=False,
        )
