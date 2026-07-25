import os
import subprocess
from pathlib import Path


def test_restore_script_refuses_source_database(tmp_path: Path) -> None:
    archive = tmp_path / "backup"
    archive.mkdir()
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql://source.example/db",
        "RESTORE_DATABASE_URL": "postgresql://source.example/db",
    }

    result = subprocess.run(
        ["bash", "scripts/restore_database.sh", str(archive)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 3
    assert "Refusing to restore into the source database" in result.stderr


def test_backup_script_requires_database_url() -> None:
    env = {key: value for key, value in os.environ.items() if key != "DATABASE_URL"}

    result = subprocess.run(
        ["bash", "scripts/backup_database.sh"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "DATABASE_URL is required" in result.stderr
