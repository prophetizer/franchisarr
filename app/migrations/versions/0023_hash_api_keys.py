"""Store user API keys as SHA-256 hashes.

Revision ID: 0023
Revises: 0022

The server only compares API keys, so it has no need to keep them; a database copy used to be
a working key for every user. Existing keys are hashed in place (same column, "sha256:" prefix),
so the keys people hold -- in an *arr import list, a dashboard widget, the CLI -- keep working.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PREFIX = "sha256:"


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, api_key FROM users WHERE api_key IS NOT NULL")).fetchall()
    for user_id, key in rows:
        if key.startswith(PREFIX):
            continue
        hashed = PREFIX + hashlib.sha256(key.strip().encode("utf-8")).hexdigest()
        connection.execute(sa.text("UPDATE users SET api_key = :h WHERE id = :i"), {"h": hashed, "i": user_id})


def downgrade() -> None:
    # A hash can't be turned back into a key. Clearing them is the honest downgrade: the old
    # code would otherwise compare plaintext against hashes and reject every key anyway.
    op.execute("UPDATE users SET api_key = NULL")
