"""add score_final + backfill + indexes

Revision ID: 5a2ea3e447f0
Revises: ee495556fd03
Create Date: 2025-09-03 21:27:36.539978

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5a2ea3e447f0'
down_revision: Union[str, None] = 'ee495556fd03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
