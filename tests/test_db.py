"""Tests for database initialization and schema."""


from anthropic_tracker.db import get_connection, get_schema_version, init_db


class TestDatabase:
    def test_init_creates_tables(self, db):
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {row["name"] for row in tables}
        assert "jobs" in table_names
        assert "departments" in table_names
        assert "offices" in table_names
        assert "daily_snapshots" in table_names
        assert "compensation" in table_names
        assert "alerts" in table_names
        assert "schema_version" in table_names

    def test_init_is_idempotent(self, db):
        init_db(db)
        init_db(db)
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert len(tables) > 0

    def test_schema_version_set(self, db):
        version = get_schema_version(db)
        assert version == 1

    def test_foreign_keys_enabled(self, db):
        result = db.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1

    def test_get_connection_in_memory(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(str(db_path))
        init_db(conn)
        assert db_path.exists()
        conn.close()
