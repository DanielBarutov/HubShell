"""Create the initial migration baseline.

Revision ID: 20260827_0001
Revises:
Create Date: 2026-08-27
"""

import typing

revision: str = "20260827_0001"
down_revision: str | None = None
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
