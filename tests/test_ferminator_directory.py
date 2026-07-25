from pathlib import Path

import pytest

from ferminator.directory import (
    parse_company_csv,
    parse_seed_html,
    slugify,
    validate_candidates,
)
from ferminator.domain import ATSProvider
from ferminator.ingestion import BoardFetch


def test_parse_seed_html_extracts_and_deduplicates_supported_boards(tmp_path: Path):
    source = tmp_path / "boards.html"
    source.write_text(
        """
        <div class="co"><div class="co-h"><span class="co-n">Example &amp; Co</span></div>
        <ul>
          <li><a href="https://job-boards.greenhouse.io/example/jobs/1">Role One</a></li>
          <li><a href="https://job-boards.greenhouse.io/example/jobs/2">Role Two</a></li>
        </ul></div>
        <div class="co"><div class="co-h"><span class="co-n">Second</span></div>
        <ul><li><a href="https://jobs.ashbyhq.com/Second/uuid">Role</a></li></ul></div>
        """,
        encoding="utf-8",
    )

    results = parse_seed_html(source)

    assert len(results) == 2
    assert results[0].board.company_name == "Example & Co"
    assert results[0].board.provider == ATSProvider.GREENHOUSE
    assert results[0].board.board_key == "example"
    assert results[1].board.provider == ATSProvider.ASHBY


def test_slugify_is_registry_safe():
    assert slugify("The AI Education Project (aiEDU)") == "the-ai-education-project-aiedu"
    assert slugify("ID.me") == "id-me"


def test_parse_company_csv_maps_supported_provider_board_keys(tmp_path: Path):
    source = tmp_path / "companies.csv"
    source.write_text(
        "company,ats,board_url\n"
        "Example,Breezy,https://example.breezy.hr\n"
        "Second,Workday,https://second.wd1.myworkdayjobs.com/en-US/External\n"
        "Third,Rippling,https://ats.rippling.com/third-careers/jobs\n"
        "Old,Jobvite,https://jobs.jobvite.com/old\n",
        encoding="utf-8",
    )

    results = parse_company_csv(source)

    assert [(item.board.provider, item.board.board_key) for item in results] == [
        (ATSProvider.BREEZY, "example"),
        (ATSProvider.WORKDAY, "second/External"),
        (ATSProvider.RIPPLING, "third-careers"),
    ]


def test_validate_candidates_captures_healthy_and_failed(monkeypatch, tmp_path: Path):
    source = tmp_path / "boards.html"
    source.write_text(
        """
        <div class="co"><div class="co-h"><span class="co-n">Good</span></div>
        <ul><li><a href="https://jobs.ashbyhq.com/good/1">Role</a></li></ul></div>
        <div class="co"><div class="co-h"><span class="co-n">Bad</span></div>
        <ul><li><a href="https://jobs.ashbyhq.com/bad/1">Role</a></li></ul></div>
        """,
        encoding="utf-8",
    )
    candidates = parse_seed_html(source)

    def fake_fetch(board):
        if board.board_key == "bad":
            raise RuntimeError("down")
        return BoardFetch(
            board=board,
            jobs=(type("Job", (), {"source_job_id": "one"})(),),
            duration_ms=12,
        )

    monkeypatch.setattr("ferminator.directory.fetch_board", fake_fetch)
    results = validate_candidates(candidates, max_workers=2)

    assert {item.candidate.board.board_key for item in results if item.healthy} == {"good"}
    failed = next(item for item in results if not item.healthy)
    assert failed.error_code == "RuntimeError"


def test_validate_candidates_rejects_structured_but_empty_board(monkeypatch, tmp_path: Path):
    source = tmp_path / "boards.html"
    source.write_text(
        """
        <div class="co"><div class="co-h"><span class="co-n">Dormant</span></div>
        <ul><li><a href="https://jobs.ashbyhq.com/dormant/1">Old role</a></li></ul></div>
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ferminator.directory.fetch_board",
        lambda board: BoardFetch(board=board, jobs=(), duration_ms=5),
    )

    result = validate_candidates(parse_seed_html(source))[0]

    assert not result.healthy
    assert result.error_code == "empty_board"


def test_validate_candidates_rejects_unsafe_worker_count():
    with pytest.raises(ValueError, match="between 1 and 16"):
        validate_candidates([], max_workers=17)
