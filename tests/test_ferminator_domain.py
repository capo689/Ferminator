from datetime import UTC, datetime, timedelta, timezone

from ferminator.domain import ATSProvider, NormalizedJob, parse_datetime


def test_parse_datetime_normalizes_naive_values_to_utc() -> None:
    parsed = parse_datetime("2026-07-23T12:34:56")

    assert parsed == datetime(2026, 7, 23, 12, 34, 56, tzinfo=UTC)


def test_parse_datetime_converts_aware_values_to_utc() -> None:
    parsed = parse_datetime(datetime(2026, 7, 23, 12, tzinfo=timezone(timedelta(hours=-7))))

    assert parsed == datetime(2026, 7, 23, 19, tzinfo=UTC)


def test_normalized_job_never_keeps_naive_datetimes() -> None:
    job = NormalizedJob(
        provider=ATSProvider.GREENHOUSE,
        board_key="example",
        source_job_id="1",
        company_slug="example",
        company_name="Example",
        title="Example role",
        job_url="https://example.com/jobs/1",
        published_at=datetime(2026, 7, 23, 12),
        retrieved_at=datetime(2026, 7, 23, 13),
    )

    assert job.published_at == datetime(2026, 7, 23, 12, tzinfo=UTC)
    assert job.retrieved_at == datetime(2026, 7, 23, 13, tzinfo=UTC)
