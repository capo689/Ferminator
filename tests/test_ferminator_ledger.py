from datetime import UTC, datetime

from ferminator.ledger import job_fingerprint, normalize_job_part, parse_master_ledger


def test_normalization_ignores_case_punctuation_location_and_parenthetical_aliases():
    assert normalize_job_part("DEPT®") == "dept"
    assert normalize_job_part("Ashley Digital (Resident)") == "ashley digital"
    assert job_fingerprint("Acme, Inc.", "AI Lead — Remote US") == (
        "acme inc::ai lead remote us"
    )


def test_master_ledger_parses_categories_dedupes_and_watchlist(tmp_path):
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        """# Ledger
**Last updated 2026-07-24**
## Applied (2)
| Company | Role | Status |
|---|---|---|
| Acme | AI Lead | Applied |
| Acme | AI Lead | Applied twice |
## Fake (1)
| Company | Role | Status |
|---|---|---|
| Scam Co | Writer | FAKE |
## Company watchlist (2)
A prior application exists.
These are not hard-suppressed.
Good Co, Other Co
""",
        encoding="utf-8",
    )
    parsed = parse_master_ledger(ledger)
    assert len(parsed.entries) == 2
    assert {entry.category for entry in parsed.entries} == {"Applied", "Fake"}
    fake = next(entry for entry in parsed.entries if entry.category == "Fake")
    assert fake.permanent and fake.suppress_until is None
    applied = next(entry for entry in parsed.entries if entry.category == "Applied")
    assert applied.suppress_until == datetime(2027, 1, 23, tzinfo=UTC)
    assert [item.company for item in parsed.company_watchlist] == ["Good Co", "Other Co"]
