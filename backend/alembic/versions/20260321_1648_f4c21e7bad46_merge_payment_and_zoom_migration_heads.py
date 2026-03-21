"""merge payment and zoom migration heads

Revision ID: f4c21e7bad46
Revises: i8j9k0l1m2n3, z0o0m1r2u3l4
Create Date: 2026-03-21 16:48:46.280586+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic
revision: str = 'f4c21e7bad46'
down_revision: Union[str, None] = ('i8j9k0l1m2n3', 'z0o0m1r2u3l4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
