"""media servers as rows

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-18 23:30:00.000000

"The media server" becomes "the media servers". The one configured through settings (media_server,
plex_url/plex_token, jellyfin_*, emby_*, plex_machine_identifier) is copied into a row of the new
media_servers table; the libraries and items already scanned are attached to that row; the old
setting rows are removed so nothing reads them by mistake. Data is untouched.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_KEYS = (
    "media_server", "plex_url", "plex_token", "jellyfin_url", "jellyfin_api_key",
    "emby_url", "emby_api_key", "plex_machine_identifier",
)
LABELS = {"plex": "Plex", "jellyfin": "Jellyfin", "emby": "Emby"}


def _legacy_settings(conn) -> dict[str, str]:
    rows = conn.execute(
        sa.text("SELECT key, value FROM settings WHERE key IN :keys").bindparams(
            sa.bindparam("keys", expanding=True)
        ),
        {"keys": list(LEGACY_KEYS)},
    )
    return {key: value for key, value in rows if value}


def _seed_server(conn) -> int | None:
    """The server the settings described, as a row. None when they described none."""
    s = _legacy_settings(conn)
    kind = (s.get("media_server") or "").strip().lower()
    if kind not in LABELS:
        # Same inference config.py used: whichever URL is set, Plex first.
        kind = next((k for k in ("plex", "jellyfin", "emby") if s.get(f"{k}_url")), "plex")
    url = s.get(f"{kind}_url")
    credential = s.get("plex_token" if kind == "plex" else f"{kind}_api_key")
    if not (url and credential):
        return None
    result = conn.execute(
        sa.text(
            "INSERT INTO media_servers (name, kind, url, credential, enabled, machine_identifier, "
            "created_at) VALUES (:name, :kind, :url, :credential, 1, :machine, CURRENT_TIMESTAMP)"
        ),
        {"name": LABELS[kind], "kind": kind, "url": url, "credential": credential,
         "machine": s.get("plex_machine_identifier") if kind == "plex" else None},
    )
    return result.lastrowid


def upgrade() -> None:
    op.create_table(
        "media_servers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("credential", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("machine_identifier", sa.String(), nullable=True),
        sa.Column("watched_user", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_media_servers_name"), "media_servers", ["name"], unique=True)

    conn = op.get_bind()
    server_id = _seed_server(conn)

    # Attach what was scanned to the server it came from. Nullable first, filled, then required.
    for table in ("included_libraries", "library_items"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("server_id", sa.Integer(), nullable=True))
        if server_id is not None:
            conn.execute(sa.text(f"UPDATE {table} SET server_id = :sid"), {"sid": server_id})
        else:
            # Rows with no server to belong to are a cache of nothing reachable; the next scan
            # would rebuild them anyway.
            conn.execute(sa.text(f"DELETE FROM {table}"))

    with op.batch_alter_table("included_libraries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_included_libraries_library_key"))
        batch_op.alter_column("server_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_included_libraries_server_id_media_servers", "media_servers", ["server_id"], ["id"]
        )
        batch_op.create_unique_constraint("uq_included_library", ["server_id", "library_key"])
    with op.batch_alter_table("included_libraries", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_included_libraries_library_key"), ["library_key"], unique=False)
        batch_op.create_index(batch_op.f("ix_included_libraries_server_id"), ["server_id"], unique=False)

    with op.batch_alter_table("library_items", schema=None) as batch_op:
        batch_op.drop_constraint("uq_library_item", type_="unique")
        batch_op.alter_column("server_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_library_items_server_id_media_servers", "media_servers", ["server_id"], ["id"]
        )
        batch_op.create_unique_constraint("uq_library_item", ["server_id", "library_key", "item_key"])
        batch_op.add_column(sa.Column("watched", sa.Boolean(), nullable=True))
    with op.batch_alter_table("library_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_library_items_server_id"), ["server_id"], unique=False)

    conn.execute(
        sa.text("DELETE FROM settings WHERE key IN :keys").bindparams(
            sa.bindparam("keys", expanding=True)
        ),
        {"keys": list(LEGACY_KEYS)},
    )


def downgrade() -> None:
    conn = op.get_bind()
    # Put the first enabled server back into settings so 0019 code can still read it.
    row = conn.execute(
        sa.text("SELECT kind, url, credential, machine_identifier FROM media_servers "
                "WHERE enabled = 1 ORDER BY id LIMIT 1")
    ).first()
    if row:
        kind, url, credential, machine = row
        values = {"media_server": kind, f"{kind}_url": url,
                  ("plex_token" if kind == "plex" else f"{kind}_api_key"): credential}
        if machine:
            values["plex_machine_identifier"] = machine
        for key, value in values.items():
            conn.execute(
                sa.text("INSERT OR REPLACE INTO settings (key, value, updated_at) "
                        "VALUES (:k, :v, CURRENT_TIMESTAMP)"),
                {"k": key, "v": value},
            )

    with op.batch_alter_table("library_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_library_items_server_id"))
        batch_op.drop_constraint("uq_library_item", type_="unique")
        batch_op.drop_constraint("fk_library_items_server_id_media_servers", type_="foreignkey")
        batch_op.drop_column("watched")
        batch_op.drop_column("server_id")
        batch_op.create_unique_constraint("uq_library_item", ["library_key", "item_key"])

    with op.batch_alter_table("included_libraries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_included_libraries_server_id"))
        batch_op.drop_index(batch_op.f("ix_included_libraries_library_key"))
        batch_op.drop_constraint("uq_included_library", type_="unique")
        batch_op.drop_constraint("fk_included_libraries_server_id_media_servers", type_="foreignkey")
        batch_op.drop_column("server_id")
    with op.batch_alter_table("included_libraries", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_included_libraries_library_key"), ["library_key"], unique=True)

    op.drop_index(op.f("ix_media_servers_name"), table_name="media_servers")
    op.drop_table("media_servers")
