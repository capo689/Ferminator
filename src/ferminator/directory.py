"""ATS directory import and live validation."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit

from ferminator.domain import ATSProvider, BoardRef
from ferminator.ingestion import fetch_board

_COMPANY_RE = re.compile(
    r'<div class="co"><div class="co-h"><span class="co-n">(.*?)</span>'
    r"(.*?)</ul></div>",
    re.DOTALL,
)
_LINK_RE = re.compile(r'<a href="(https://[^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class DirectoryCandidate:
    board: BoardRef
    seed_job_url: str
    seed_job_title: str


@dataclass(frozen=True)
class BoardValidation:
    candidate: DirectoryCandidate
    healthy: bool
    job_count: int | None
    error_code: str | None
    duration_ms: int


def _text(value: str) -> str:
    return unescape(_TAG_RE.sub("", value)).strip()


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized[:126]


def parse_seed_html(path: str | Path) -> list[DirectoryCandidate]:
    """Extract unique Greenhouse and Ashby boards from a saved master list."""
    html = Path(path).read_text(encoding="utf-8")
    candidates: dict[tuple[ATSProvider, str], DirectoryCandidate] = {}
    for company_match in _COMPANY_RE.finditer(html):
        company_name = _text(company_match.group(1))
        for link_match in _LINK_RE.finditer(company_match.group(2)):
            url = unescape(link_match.group(1))
            parsed = urlsplit(url)
            parts = [part for part in parsed.path.split("/") if part]
            if not parts:
                continue
            if parsed.hostname and parsed.hostname.endswith("greenhouse.io"):
                provider = ATSProvider.GREENHOUSE
                board_key = parts[0]
                source_url = f"https://job-boards.greenhouse.io/{board_key}"
                region = "eu" if ".eu.greenhouse.io" in parsed.hostname else "global"
            elif parsed.hostname == "jobs.ashbyhq.com":
                provider = ATSProvider.ASHBY
                board_key = parts[0]
                source_url = f"https://jobs.ashbyhq.com/{board_key}"
                region = "global"
            else:
                continue
            identity = (provider, board_key.casefold())
            candidates[identity] = DirectoryCandidate(
                board=BoardRef(
                    provider=provider,
                    company_slug=slugify(company_name),
                    company_name=company_name,
                    board_key=board_key,
                    source_url=source_url,
                    region=region,
                ),
                seed_job_url=url,
                seed_job_title=_text(link_match.group(2)),
            )
    return sorted(
        candidates.values(),
        key=lambda item: (item.board.company_name.casefold(), item.board.provider.value),
    )


def validate_candidates(
    candidates: list[DirectoryCandidate],
    *,
    max_workers: int = 8,
) -> list[BoardValidation]:
    """Test candidate boards through production adapters with bounded concurrency."""
    if max_workers < 1 or max_workers > 16:
        raise ValueError("max_workers must be between 1 and 16")
    results: list[BoardValidation] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(candidates))) as executor:
        futures = {
            executor.submit(fetch_board, candidate.board): candidate
            for candidate in candidates
        }
        for future in as_completed(futures):
            candidate = futures[future]
            try:
                fetched = future.result()
                has_jobs = bool(fetched.jobs)
                results.append(
                    BoardValidation(
                        candidate=candidate,
                        healthy=has_jobs,
                        job_count=len(fetched.jobs),
                        error_code=None if has_jobs else "empty_board",
                        duration_ms=fetched.duration_ms,
                    )
                )
            except Exception as exc:
                results.append(
                    BoardValidation(
                        candidate=candidate,
                        healthy=False,
                        job_count=None,
                        error_code=str(getattr(exc, "code", type(exc).__name__))[:120],
                        duration_ms=0,
                    )
                )
    return sorted(results, key=lambda item: item.candidate.board.company_name.casefold())
