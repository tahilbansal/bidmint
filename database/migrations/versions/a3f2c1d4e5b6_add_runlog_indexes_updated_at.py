"""add run_logs table, indexes, updated_at on suppliers

Revision ID: a3f2c1d4e5b6
Revises: 8941bb461b0c
Create Date: 2026-03-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f2c1d4e5b6'
down_revision: Union[str, None] = '8941bb461b0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- run_logs table ---
    op.create_table(
        'run_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('job_name', sa.String(length=50), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('scraped', sa.Integer(), nullable=True),
        sa.Column('new_tenders', sa.Integer(), nullable=True),
        sa.Column('alerts_sent', sa.Integer(), nullable=True),
        sa.Column('errors', sa.Integer(), nullable=True),
        sa.Column('error_detail', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_run_logs_started_at', 'run_logs', ['started_at'])
    op.create_index('ix_run_logs_job_name',   'run_logs', ['job_name'])

    # --- updated_at on suppliers ---
    op.add_column('suppliers', sa.Column('updated_at', sa.DateTime(), nullable=True))

    # --- indexes on tenders ---
    op.create_index('ix_tenders_scraped_at', 'tenders', ['scraped_at'])
    op.create_index('ix_tenders_category',   'tenders', ['category'])
    op.create_index('ix_tenders_source',     'tenders', ['source'])

    # --- indexes on alerts ---
    op.create_index('ix_alerts_sent_at',     'alerts', ['sent_at'])
    op.create_index('ix_alerts_supplier_id', 'alerts', ['supplier_id'])
    op.create_index('ix_alerts_tender_id',   'alerts', ['tender_id'])


def downgrade() -> None:
    op.drop_index('ix_alerts_tender_id',   table_name='alerts')
    op.drop_index('ix_alerts_supplier_id', table_name='alerts')
    op.drop_index('ix_alerts_sent_at',     table_name='alerts')
    op.drop_index('ix_tenders_source',     table_name='tenders')
    op.drop_index('ix_tenders_category',   table_name='tenders')
    op.drop_index('ix_tenders_scraped_at', table_name='tenders')
    op.drop_column('suppliers', 'updated_at')
    op.drop_index('ix_run_logs_job_name',   table_name='run_logs')
    op.drop_index('ix_run_logs_started_at', table_name='run_logs')
    op.drop_table('run_logs')
