"""create initial schema

Revision ID: create_initial_schema
Revises: 20250904_add_score_final
Create Date: 2025-09-06 12:22:00.000000

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'create_initial_schema'
down_revision: Union[str, None] = '20250904_add_score_final'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create search_runs table
    op.create_table(
        'search_runs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create records table
    op.create_table(
        'records',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('abstract', sa.Text(), nullable=True),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('doi', sa.String(), nullable=True),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['search_runs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_records_run_id'), 'records', ['run_id'], unique=False)
    op.create_index(op.f('ix_records_doi'), 'records', ['doi'], unique=False)

    # Create appraisals table
    op.create_table(
        'appraisals',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('record_id', sa.String(), nullable=False),
        sa.Column('rating', sa.String(), nullable=False),
        sa.Column('scores_json', sa.Text(), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('citations_json', sa.Text(), nullable=True),
        sa.Column('score_final', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['record_id'], ['records.id'], ),
        sa.ForeignKeyConstraint(['run_id'], ['search_runs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_appraisals_run_id'), 'appraisals', ['run_id'], unique=False)
    op.create_index(op.f('ix_appraisals_record_id'), 'appraisals', ['record_id'], unique=False)

    # Create screenings table
    op.create_table(
        'screenings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('record_id', sa.String(), nullable=False),
        sa.Column('decision', sa.String(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['record_id'], ['records.id'], ),
        sa.ForeignKeyConstraint(['run_id'], ['search_runs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_screenings_run_id'), 'screenings', ['run_id'], unique=False)
    op.create_index(op.f('ix_screenings_record_id'), 'screenings', ['record_id'], unique=False)

    # Create prisma_counts table
    op.create_table(
        'prisma_counts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('identified', sa.Integer(), nullable=True),
        sa.Column('deduped', sa.Integer(), nullable=True),
        sa.Column('screened', sa.Integer(), nullable=True),
        sa.Column('excluded', sa.Integer(), nullable=True),
        sa.Column('eligible', sa.Integer(), nullable=True),
        sa.Column('included', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['search_runs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prisma_counts_run_id'), 'prisma_counts', ['run_id'], unique=True)


def downgrade() -> None:
    op.drop_table('prisma_counts')
    op.drop_table('screenings')
    op.drop_table('appraisals')
    op.drop_table('records')
    op.drop_table('search_runs')