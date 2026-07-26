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
            "salary_interval": "year",
            "compensation_text": None,
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
    assert "max(pm.profile_version)" in sql
    assert "p.match_version = m.profile_version" in sql
    assert "m.job_revision_id = j.current_revision_id" not in sql


def test_web_matches_extracts_compensation_from_stored_full_description() -> None:
    repository = object.__new__(PostgresRepository)
    repository.connection = MagicMock()
    connection = repository.connection.return_value.__enter__.return_value
    connection.execute.return_value.fetchall.return_value = [
        {
            "id": "job-id",
            "title": "Creative Director",
            "company_name": "Example",
            "company_slug": "example",
            "department": "Creative",
            "workplace_type": "remote",
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_interval": None,
            "compensation_text": "The annual base salary range is $175,000–$215,000.",
            "job_url": "https://example.com/job",
            "apply_url": None,
            "published_at": datetime.now(UTC),
            "first_seen_at": datetime.now(UTC),
            "provider": "greenhouse",
            "score": 90,
            "component_scores": {},
            "matched_evidence": [],
            "concerns": [],
            "explanation": "Strong match",
            "location": "Remote — United States",
            "history_candidates": [],
        }
    ]

    match = repository.web_matches("adam-cagle")[0]

    assert match["compensation"] is None
    assert match["compensation_text"].startswith("The annual base")
    sql = connection.execute.call_args.args[0]
    assert "r.description_text as compensation_text" in sql
    assert "substring(" not in sql


def test_job_description_uses_last_complete_score_set_during_rescan() -> None:
    repository = object.__new__(PostgresRepository)
    repository.connection = MagicMock()
    connection = repository.connection.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.return_value = {
        "description_text": "The complete stored job description."
    }

    description = repository.job_description("adam-cagle", "job-id")

    assert description == "The complete stored job description."
    sql, params = connection.execute.call_args.args
    assert "max(pm.profile_version)" in sql
    assert "p.match_version = m.profile_version" in sql
    assert "m.job_revision_id = j.current_revision_id" not in sql
    assert params == ("adam-cagle", "job-id")


def test_market_intelligence_returns_current_funnel_provider_and_gates() -> None:
    repository = object.__new__(PostgresRepository)
    repository.connection = MagicMock()
    connection = repository.connection.return_value.__enter__.return_value
    overview_cursor = MagicMock()
    overview_cursor.fetchone.return_value = {
        "active_jobs": 1000,
        "eligible_jobs": 10,
        "maximum_score": 77.5,
    }
    provider_cursor = MagicMock()
    provider_cursor.fetchall.return_value = [
        {
            "provider": "greenhouse",
            "board_count": 10,
            "active_jobs": 900,
            "eligible_jobs": 9,
            "strong_jobs": 2,
        }
    ]
    exclusion_cursor = MagicMock()
    exclusion_cursor.fetchall.return_value = [
        {"concern": "No target title", "count": 800}
    ]
    connection.execute.side_effect = [
        overview_cursor,
        provider_cursor,
        exclusion_cursor,
    ]

    intelligence = repository.market_intelligence("adam-cagle")

    assert intelligence["overview"]["active_jobs"] == 1000
    assert intelligence["providers"][0]["strong_jobs"] == 2
    assert intelligence["exclusions"][0]["count"] == 800
    assert all(
        call.args[1] == ("adam-cagle",)
        for call in connection.execute.call_args_list
    )
    provider_sql = connection.execute.call_args_list[1].args[0]
    assert "m.job_revision_id = j.current_revision_id" in provider_sql


def test_active_jobs_hydrates_compact_payload_with_canonical_description() -> None:
    repository = object.__new__(PostgresRepository)
    repository.connection = MagicMock()
    connection = repository.connection.return_value.__enter__.return_value
    connection.execute.return_value.fetchall.return_value = [
        {
            "job_id": "job-id",
            "revision_id": "revision-id",
            "normalized_payload": {
                "provider": "greenhouse",
                "board_key": "example",
                "source_job_id": "123",
                "company_slug": "example",
                "company_name": "Example",
                "title": "Creative Director",
                "job_url": "https://example.com/job",
            },
            "description_text": "Canonical complete job description.",
        }
    ]

    jobs = repository.active_jobs()

    assert jobs[0][2].description_text == "Canonical complete job description."
    assert jobs[0][2].description_html is None
    assert "r.description_text" in connection.execute.call_args.args[0]


def test_pipeline_reads_actions_directly_so_closed_listings_do_not_disappear() -> None:
    repository = object.__new__(PostgresRepository)
    repository.connection = MagicMock()
    connection = repository.connection.return_value.__enter__.return_value
    jobs_cursor = MagicMock()
    jobs_cursor.fetchall.return_value = []
    events_cursor = MagicMock()
    events_cursor.fetchall.return_value = []
    connection.execute.side_effect = [jobs_cursor, events_cursor]

    pipeline = repository.pipeline("adam-cagle")

    assert list(pipeline["stages"]) == [
        "Considering",
        "Preparing",
        "Applied",
        "Interviewing",
        "Offer",
    ]
    job_sql = connection.execute.call_args_list[0].args[0]
    assert "join public.jobs j on j.id = a.job_id" in job_sql
    assert "j.active" not in job_sql.split("where p.slug", 1)[1]


def test_unsave_deletes_bookmark_without_dismissing_or_suppressing_job() -> None:
    repository = object.__new__(PostgresRepository)
    repository.connection = MagicMock()
    connection = repository.connection.return_value.__enter__.return_value
    select_cursor = MagicMock()
    select_cursor.fetchone.return_value = {
        "id": "action-id",
        "profile_id": "profile-id",
        "job_id": "job-id",
        "state": "considering",
    }
    connection.execute.side_effect = [select_cursor, MagicMock(), MagicMock()]

    previous = repository.unsave_action("adam-cagle", "job-id")

    assert previous == "considering"
    statements = [call.args[0].casefold() for call in connection.execute.call_args_list]
    assert any("event_type" in sql and "'unsaved'" in sql for sql in statements)
    assert any("delete from public.job_actions" in sql for sql in statements)
    assert all("job_history" not in sql for sql in statements)


def test_state_change_records_both_sides_for_reliable_undo() -> None:
    repository = object.__new__(PostgresRepository)
    repository.connection = MagicMock()
    connection = repository.connection.return_value.__enter__.return_value
    previous_cursor = MagicMock()
    previous_cursor.fetchone.return_value = {
        "id": "action-id",
        "state": "considering",
    }
    upsert_cursor = MagicMock()
    upsert_cursor.fetchone.return_value = {
        "id": "action-id",
        "profile_id": "profile-id",
        "job_id": "job-id",
    }
    connection.execute.side_effect = [previous_cursor, upsert_cursor, MagicMock()]

    change = repository.set_action("adam-cagle", "job-id", "preparing")

    assert change == {"from_state": "considering", "to_state": "preparing"}
    event_call = connection.execute.call_args_list[-1]
    assert "'state_changed'" in event_call.args[0]
    assert event_call.args[1][-2:] == ("considering", "preparing")
    upsert_sql = connection.execute.call_args_list[1].args[0]
    assert "j.active" in upsert_sql
    assert "public.job_actions existing" in upsert_sql


def test_undo_of_first_save_removes_only_the_pipeline_action() -> None:
    repository = object.__new__(PostgresRepository)
    repository.connection = MagicMock()
    connection = repository.connection.return_value.__enter__.return_value
    event_cursor = MagicMock()
    event_cursor.fetchone.return_value = {
        "id": "event-id",
        "event_type": "state_changed",
        "from_state": None,
        "to_state": "considering",
        "profile_id": "profile-id",
    }
    connection.execute.side_effect = [
        event_cursor,
        MagicMock(),
        MagicMock(),
        MagicMock(),
    ]

    restored = repository.undo_action("adam-cagle", "job-id")

    assert restored is None
    statements = [call.args[0].casefold() for call in connection.execute.call_args_list]
    assert any("delete from public.job_actions" in sql for sql in statements)
    assert any("'undo'" in sql for sql in statements)
    assert any("state_change_undone" in sql for sql in statements)
