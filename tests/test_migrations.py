from __future__ import annotations

import sqlite3

from alembic import command
from alembic.config import Config

from app.core.config import get_settings


def _table_names(database_path) -> set[str]:
    connection = sqlite3.connect(database_path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()


def test_initial_migration_upgrades_and_downgrades(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "migrations.db"
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{database_path}",
    )
    get_settings.cache_clear()
    alembic_config = Config("alembic.ini")

    try:
        command.upgrade(alembic_config, "head")
        assert {"alembic_version", "conversations", "messages"}.issubset(
            _table_names(database_path)
        )

        command.check(alembic_config)
        command.downgrade(alembic_config, "base")
        assert "conversations" not in _table_names(database_path)
        assert "messages" not in _table_names(database_path)
    finally:
        get_settings.cache_clear()
