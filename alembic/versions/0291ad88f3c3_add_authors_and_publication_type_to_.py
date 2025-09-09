"""add authors and publication_type to records

Revision ID: 0291ad88f3c3
Revises: create_initial_schema
Create Date: 2025-09-07 11:57:40.546877

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0291ad88f3c3'
down_revision: Union[str, None] = 'create_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
