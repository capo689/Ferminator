from ferminator.digest import compose_digest


def test_digest_is_stable_for_same_day_and_matches() -> None:
    matches = [
        {
            "title": "Director, AI Enablement",
            "company_name": "Airtable",
            "score": 94,
            "job_url": "https://example.com/job",
        }
    ]
    first = compose_digest("Adam", matches)
    second = compose_digest("Adam", matches)

    assert first.idempotency_key == second.idempotency_key
    assert "Director, AI Enablement" in first.text
    assert "94% match" in first.text
    assert "Airtable" in first.html


def test_empty_digest_is_truthful() -> None:
    digest = compose_digest("Adam", [])

    assert "No new high-confidence matches" in digest.text
    assert "0 opportunities" in digest.subject
