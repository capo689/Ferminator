from datetime import UTC, datetime
from unittest.mock import MagicMock

from ferminator.domain import ATSProvider, NormalizedJob
from ferminator.matching import MatchResult
from ferminator.repository import PostgresRepository, jobs_requiring_upsert


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


def test_jobs_requiring_upsert_skips_unchanged_and_counts_updates() -> None:
    unchanged = NormalizedJob(
        provider=ATSProvider.GREENHOUSE,
        board_key="example",
        source_job_id="same",
        company_slug="example",
        company_name="Example",
        title="Same",
        job_url="https://example.com/same",
    )
    updated = unchanged.model_copy(
        update={"source_job_id": "updated", "title": "Materially updated"}
    )
    new = unchanged.model_copy(update={"source_job_id": "new", "title": "New"})
    current_hashes = {
        unchanged.source_key: unchanged.content_hash,
        updated.source_key: "old-hash",
    }

    changed, updated_count = jobs_requiring_upsert(
        [unchanged, updated, new],
        current_hashes,
    )

    assert [job.source_job_id for job in changed] == ["updated", "new"]
    assert updated_count == 1


def test_web_matches_keeps_fuzzy_prior_application_visible_with_warning() -> None:
    repository = object.__new__(PostgresRepository)
    repository.connection = MagicMock()
    connection = repository.connection.return_value.__enter__.return_value
    connection.execute.return_value.fetchall.return_value = [
        {
            "id": "job-id",
            "title": "Director, AI Enablement",
            "company_name": "Intradiem",
            "company_slug": "intradiem",
            "department": "AI",
            "workplace_type": "remote",
            "salary_min": 180000,
            "salary_max": 220000,
            "salary_currency": "USD",
            "job_url": "https://example.com/job",
            "apply_url": "https://example.com/apply",
            "published_at": datetime.now(UTC),
            "first_seen_at": datetime.now(UTC),
            "provider": "greenhouse",
            "score": 82,
            "component_scores": {},
            "matched_evidence": [],
            "concerns": [],
            "explanation": "Calibration match",
            "location": "Remote — United States",
            "history_candidates": [
                {
                    "title": "Director, Enterprise AI Enablement",
                    "category": "Applied",
                    "status": "Applied",
                    "applied_at": datetime(2026, 7, 20, tzinfo=UTC),
                    "first_recorded_at": datetime(2026, 7, 20, tzinfo=UTC),
                }
            ],
        }
    ]

    matches = repository.web_matches("adam-cagle")

    assert len(matches) == 1
    assert matches[0]["prior_application"]["is_applied"]
    assert matches[0]["prior_application"]["confidence"] == 0.96
    sql = connection.execute.call_args.args[0]
    assert "history_candidates" in sql
    assert "(h.permanent or h.suppress_until > now())" in sql
