from unittest.mock import MagicMock

from ferminator.matching import MatchResult
from ferminator.repository import PostgresRepository


def test_store_matches_uses_psycopg_cursor_executemany() -> None:
    repository = object.__new__(PostgresRepository)
    repository.connection = MagicMock()
    connection = repository.connection.return_value.__enter__.return_value
    cursor = connection.cursor.return_value.__enter__.return_value

    repository.store_matches(
        profile_id="profile-id",
        profile_version=3,
        matches=[
            (
                "job-id",
                "revision-id",
                MatchResult(eligible=True, score=72, explanation="Strong match"),
            )
        ],
    )

    cursor.executemany.assert_called_once()
    connection.executemany.assert_not_called()
