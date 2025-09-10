"""add extended metadata fields

Revision ID: e9ab59836f6b
Revises: 0291ad88f3c3
Create Date: 2025-09-10 15:55:22.258741

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e9ab59836f6b'
down_revision: Union[str, None] = '0291ad88f3c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
