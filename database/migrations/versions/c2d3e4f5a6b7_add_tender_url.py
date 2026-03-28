"""add tender_url column to tenders

Revision ID: c2d3e4f5a6b7
Revises: a3f2c1d4e5b6
Create Date: 2026-03-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'a3f2c1d4e5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tenders',
        sa.Column('tender_url', sa.String(length=500), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('tenders', 'tender_url')
