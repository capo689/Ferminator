from unittest.mock import MagicMock

from ferminator.matching import MatchResult
from ferminator.repository import PostgresRepository


def test_store_matches_uses_psycopg_cursor_executemany() -> None:
    repository = object.__new__(PostgresRepository)
    repository.connection = MagicMock()
    connection = repository.connection.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.return_value = {"acquired": True}
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
    assert "pg_try_advisory_xact_lock" in connection.execute.call_args_list[2].args[0]
    assert "is distinct from" in cursor.executemany.call_args.args[0].casefold()


def test_match_feedback_is_upserted_against_current_revision() -> None:
    repository = object.__new__(PostgresRepository)
    repository.connection = MagicMock()
    connection = repository.connection.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.return_value = {"id": "feedback-id"}

    repository.set_match_feedback(
        "adam-cagle",
        "job-id",
        "wrong",
        reason="Wrong discipline",
    )

    sql, params = connection.execute.call_args.args
    assert "match_feedback" in sql
    assert "job_revision_id" in sql
    assert params == ("wrong", "Wrong discipline", "job-id", "adam-cagle")
