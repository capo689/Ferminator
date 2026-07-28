"""Ferminator command-line interface."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.table import Table

from ferminator.adapters import ADAPTERS
from ferminator.digest import compose_digest, send_smtp
from ferminator.directory import parse_company_csv, parse_seed_html, validate_candidates
from ferminator.discover_visibility import (
    apply_default_discover_filters,
    apply_role_thresholds,
)
from ferminator.domain import ATSProvider, BoardRef
from ferminator.ingestion import IngestionResult, run_bulk_ingestion
from ferminator.ledger import parse_master_ledger
from ferminator.matching import score_job
from ferminator.profiles import load_profile
from ferminator.quality import evaluate_quality
from ferminator.registry import load_registry
from ferminator.repository import PostgresRepository

console = Console()


@click.group()
def cli() -> None:
    """Ferminator career intelligence."""


@cli.group()
def profile() -> None:
    """Validate and inspect named career profiles."""


@cli.command("ledger-import")
@click.option("--profile-slug", default="adam-cagle", show_default=True)
@click.argument("ledger_path", type=click.Path(exists=True, path_type=Path))
def ledger_import(profile_slug: str, ledger_path: Path) -> None:
    """Import a Markdown master ledger into durable duplicate suppression."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise click.ClickException("DATABASE_URL is required")
    parsed = parse_master_ledger(ledger_path)
    repository = PostgresRepository(database_url)
    try:
        history_count, watch_count = repository.import_ledger(profile_slug, parsed)
    finally:
        repository.close()
    console.print(
        f"[green]Imported {history_count} job-history entries and "
        f"{watch_count} company warnings for {profile_slug}[/green]"
    )


@profile.command("validate")
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
def validate_profiles(paths: tuple[Path, ...]) -> None:
    """Validate one or more Markdown profiles."""
    targets = paths or tuple(sorted(Path("profiles").glob("*.md")))
    if not targets:
        raise click.ClickException("No profile files found")
    table = Table("Profile", "Cadence", "Targets", "Status")
    for path in targets:
        parsed = load_profile(path)
        target_count = len(parsed.high_titles) + len(parsed.adjacent_titles)
        table.add_row(
            parsed.profile.display_name,
            f"{parsed.search.scan_interval_hours}h",
            str(target_count),
            "[green]valid[/green]",
        )
    console.print(table)


@cli.command("ats-smoke")
@click.option("--provider", type=click.Choice([item.value for item in ATSProvider]), required=True)
@click.option("--board-key", required=True)
@click.option("--company-slug", required=True)
@click.option("--company-name", required=True)
@click.option("--source-url", required=True)
@click.option("--region", default="global")
def ats_smoke(
    provider: str,
    board_key: str,
    company_slug: str,
    company_name: str,
    source_url: str,
    region: str,
) -> None:
    """Run a bounded live ATS adapter smoke test."""
    provider_type = ATSProvider(provider)
    board = BoardRef(
        provider=provider_type,
        board_key=board_key,
        company_slug=company_slug,
        company_name=company_name,
        source_url=source_url,
        region=region,
    )
    with ADAPTERS[provider_type]() as adapter:
        jobs = adapter.fetch_jobs(board)
    console.print(f"[green]{provider}[/green]: normalized {len(jobs)} jobs")
    if jobs:
        console.print(f"First: {jobs[0].title} ({jobs[0].source_key})")


@cli.command("registry-validate")
def registry_validate() -> None:
    """Validate the private database registry without printing its contents."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise click.ClickException("DATABASE_URL is required")
    repository = PostgresRepository(database_url)
    boards = repository.enabled_boards()
    if not boards:
        raise click.ClickException("Private registry contains no enabled boards")
    providers = sorted({board.provider.value for board in boards})
    console.print(
        f"[green]Private registry valid[/green]: {len(boards)} enabled boards "
        f"across {len(providers)} providers"
    )


@cli.command("registry-import")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def registry_import(path: Path) -> None:
    """Import a private local registry file into Postgres."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise click.ClickException("DATABASE_URL is required")
    registry = load_registry(path)
    repository = PostgresRepository(database_url)
    companies, boards = repository.sync_registry(registry)
    console.print(
        f"[green]Private registry imported[/green]: {companies} companies, {boards} boards"
    )


@cli.command("directory-check")
@click.argument("seed_path", type=click.Path(exists=True, path_type=Path))
@click.option("--workers", default=8, type=click.IntRange(1, 16), show_default=True)
@click.option("--json-output", type=click.Path(path_type=Path))
def directory_check(seed_path: Path, workers: int, json_output: Path | None) -> None:
    """Extract and live-test public ATS boards from an HTML or CSV directory."""
    candidates = (
        parse_company_csv(seed_path)
        if seed_path.suffix.casefold() == ".csv"
        else parse_seed_html(seed_path)
    )
    results = validate_candidates(candidates, max_workers=workers)
    table = Table("Company", "Provider", "Board", "Jobs", "Status")
    for result in results:
        board = result.candidate.board
        table.add_row(
            board.company_name,
            board.provider.value,
            board.board_key,
            str(result.job_count) if result.job_count is not None else "—",
            "[green]healthy[/green]" if result.healthy else f"[red]{result.error_code}[/red]",
        )
    console.print(table)
    payload = {
        "source": str(seed_path),
        "checked_at": datetime.now(UTC).isoformat(),
        "total": len(results),
        "healthy": sum(result.healthy for result in results),
        "failed": sum(not result.healthy for result in results),
        "results": [
            {
                "company": result.candidate.board.company_name,
                "company_slug": result.candidate.board.company_slug,
                "provider": result.candidate.board.provider.value,
                "board_key": result.candidate.board.board_key,
                "region": result.candidate.board.region,
                "source_url": str(result.candidate.board.source_url),
                "seed_job_url": result.candidate.seed_job_url,
                "seed_job_title": result.candidate.seed_job_title,
                "healthy": result.healthy,
                "job_count": result.job_count,
                "duration_ms": result.duration_ms,
                "error_code": result.error_code,
            }
            for result in results
        ],
    }
    if json_output:
        json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        console.print(f"Evidence written to {json_output}")
    if payload["failed"]:
        raise click.ClickException(f"{payload['failed']} board(s) failed validation")


@cli.command("directory-merge")
@click.argument("validation_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--registry",
    "registry_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
)
@click.option("--output", type=click.Path(path_type=Path), required=True)
def directory_merge(validation_path: Path, registry_path: Path, output: Path) -> None:
    """Merge only live-validated boards into an existing registry."""
    evidence = json.loads(validation_path.read_text(encoding="utf-8"))
    registry = load_registry(registry_path)
    payload = registry.model_dump(mode="json", exclude_none=True)
    companies = payload["companies"]
    by_slug = {company["slug"]: company for company in companies}
    identities = {
        (board["provider"], board["board_key"].casefold(), board["region"])
        for company in companies
        for board in company["boards"]
    }
    added = 0
    for row in evidence.get("results", []):
        if not row.get("healthy"):
            continue
        identity = (
            row["provider"],
            row["board_key"].casefold(),
            row.get("region", "global"),
        )
        if identity in identities:
            continue
        slug = row["company_slug"]
        company = by_slug.get(slug)
        if company is None:
            company = {
                "slug": slug,
                "name": row["company"],
                "enabled": True,
                "priority": 50,
                "boards": [],
            }
            companies.append(company)
            by_slug[slug] = company
        company["boards"].append(
            {
                "provider": row["provider"],
                "board_key": row["board_key"],
                "source_url": row["source_url"],
                "region": row.get("region", "global"),
                "enabled": True,
            }
        )
        identities.add(identity)
        added += 1
    companies.sort(key=lambda company: company["name"].casefold())
    output.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    load_registry(output)
    console.print(
        f"[green]Added {added} validated boards; "
        f"{len(identities)} total boards written to {output}[/green]"
    )


@cli.command("quality-eval")
@click.option(
    "--profile-path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("profiles/adam-cagle.md"),
)
@click.option(
    "--fixtures",
    type=click.Path(exists=True, path_type=Path),
    default=Path("tests/golden/adam-match-quality.yaml"),
)
@click.option("--minimum-accuracy", default=80.0, type=click.FloatRange(0, 100))
def quality_eval(profile_path: Path, fixtures: Path, minimum_accuracy: float) -> None:
    """Evaluate ranking against human-labelled good, review, and wrong jobs."""
    report = evaluate_quality(load_profile(profile_path), fixtures)
    table = Table("Case", "Expected", "Predicted", "Score", "Result")
    for case in report.cases:
        table.add_row(
            case["name"],
            case["expected"],
            case["predicted"],
            f"{case['score']:.1f}",
            "[green]pass[/green]" if case["correct"] else "[red]fail[/red]",
        )
    console.print(table)
    console.print(
        f"Accuracy {report.accuracy:.1f}% · false positives {report.false_positives} · "
        f"false negatives {report.false_negatives}"
    )
    if report.accuracy < minimum_accuracy or report.false_positives:
        raise click.ClickException("Match-quality gate failed")


def _boards_for_shard(
    boards: list[BoardRef],
    *,
    shard_index: int,
    shard_count: int,
) -> list[BoardRef]:
    """Assign board identities to stable, non-overlapping scan shards."""
    if shard_count == 1:
        return boards
    selected = []
    for board in boards:
        identity = (f"{board.provider.value}:{board.board_key.casefold()}:{board.region}").encode()
        assigned = int.from_bytes(hashlib.sha256(identity).digest()[:8], "big")
        if assigned % shard_count + 1 == shard_index:
            selected.append(board)
    return selected


@cli.command("rescore")
@click.option(
    "--profile-path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("profiles/adam-cagle.md"),
    show_default=True,
)
def rescore(profile_path: Path) -> None:
    """Refresh one profile's matches from the shared job corpus without fetching ATS boards."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise click.ClickException("DATABASE_URL is required")
    career_profile = load_profile(profile_path)
    repository = PostgresRepository(database_url)
    try:
        profile_id = repository.sync_profile(
            career_profile,
            os.environ.get(career_profile.profile.email_env),
        )
        profile_version = repository.profile_version(profile_id)
        active_jobs = repository.active_jobs()
        scored_matches = [
            (job_id, revision_id, score_job(career_profile, job))
            for job_id, revision_id, job in active_jobs
        ]
        repository.store_matches(
            profile_id=profile_id,
            profile_version=profile_version,
            matches=scored_matches,
        )
    finally:
        repository.close()
    console.print(
        f"[green]{career_profile.profile.display_name}: rescored "
        f"{len(active_jobs)} active jobs[/green]"
    )
    gateway_counts = Counter(
        (
            match.explanation.split(" — ", 1)[0]
            if match.explanation.startswith("Gateway ")
            else "Legacy/unclassified"
        )
        for _, _, match in scored_matches
    )
    table = Table("Gateway outcome", "Jobs")
    for gateway, count in sorted(gateway_counts.items()):
        table.add_row(gateway, f"{count:,}")
    console.print(table)


@cli.command("discover-audit")
@click.option(
    "--profile-path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("profiles/adam-cagle.md"),
    show_default=True,
)
@click.option("--minimum-visible", type=click.IntRange(1), default=1, show_default=True)
def discover_audit(profile_path: Path, minimum_visible: int) -> None:
    """Verify the actual default Discover result after every suppression layer."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise click.ClickException("DATABASE_URL is required")
    career_profile = load_profile(profile_path)
    repository = PostgresRepository(database_url)
    try:
        database_matches = repository.web_matches(
            career_profile.profile.slug,
            minimum_score=0,
            limit=5000,
        )
        thresholded = apply_role_thresholds(
            career_profile,
            database_matches,
            repository.role_thresholds(career_profile.profile.slug),
        )
        visible = apply_default_discover_filters(career_profile, thresholded)
    finally:
        repository.close()
    console.print(
        f"{career_profile.profile.display_name}: "
        f"{len(database_matches)} eligible after ledger suppression · "
        f"{len(thresholded)} after role thresholds · "
        f"{len(visible)} visible with default feedback and geography"
    )
    if len(visible) < minimum_visible:
        raise click.ClickException(
            f"Default Discover has {len(visible)} jobs; expected at least {minimum_visible}"
        )


@cli.command("scan")
@click.option("--provider", type=click.Choice([item.value for item in ATSProvider]))
@click.option("--company")
@click.option("--workers", default=8, type=click.IntRange(1, 16), show_default=True)
@click.option("--shard-index", default=1, type=click.IntRange(1, 64), show_default=True)
@click.option("--shard-count", default=1, type=click.IntRange(1, 64), show_default=True)
def scan(
    provider: str | None,
    company: str | None,
    workers: int,
    shard_index: int,
    shard_count: int,
) -> None:
    """Ingest enabled public boards into Postgres."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise click.ClickException("DATABASE_URL is required")
    repository = PostgresRepository(database_url)
    boards = repository.enabled_boards()
    if provider:
        boards = [board for board in boards if board.provider.value == provider]
    if company:
        boards = [board for board in boards if board.company_slug == company]
    if shard_index > shard_count:
        raise click.ClickException("shard-index cannot be greater than shard-count")
    boards = _boards_for_shard(boards, shard_index=shard_index, shard_count=shard_count)
    if not boards:
        raise click.ClickException("No enabled boards match the filters")
    failed = False
    succeeded = 0
    errors: list[str] = []
    scored_jobs = 0
    scan_identity = (
        f"{datetime.now(UTC).strftime('%Y%m%d%H')}:"
        f"{provider or 'all'}:{company or 'all'}:{shard_index}/{shard_count}"
    )
    scan_key = hashlib.sha256(scan_identity.encode()).hexdigest()
    scan_id: str | None = None
    try:
        with repository.scan_lock():
            interrupted = repository.fail_interrupted_scans()
            if interrupted:
                console.print(
                    f"[yellow]Reconciled {interrupted} interrupted scan record(s)[/yellow]"
                )
            scan_id = repository.start_scan(scan_key, len(boards))
            # Push any file-backed profiles into the database first so editing
            # profiles/*.md keeps working, then take the authoritative list from
            # the database. Accounts provisioned through /admin exist only as
            # rows, so globbing the filesystem silently skipped them and they
            # were never scored.
            for profile_path in sorted(Path("profiles").glob("*.md")):
                disk_profile = load_profile(profile_path)
                if disk_profile.search.enabled:
                    repository.sync_profile(
                        disk_profile,
                        os.environ.get(disk_profile.profile.email_env),
                    )
            scannable = [
                (profile_id, career_profile)
                for profile_id, career_profile in repository.scannable_profiles()
                if career_profile.search.enabled
            ]
            profiles = [career_profile for _, career_profile in scannable]
            profile_ids = {
                career_profile.profile.slug: profile_id for profile_id, career_profile in scannable
            }
            console.print(f"[cyan]Scoring {len(profiles)} profile(s) from the database[/cyan]")

            def report(
                board: BoardRef,
                result: IngestionResult | None,
                error_code: str | None,
            ) -> None:
                if result:
                    console.print(
                        f"[green]{board.company_name}[/green] "
                        f"{result.fetched} fetched, {result.added} added, "
                        f"{result.updated} updated, {result.removed} removed, "
                        f"{result.reactivated} reactivated"
                    )
                else:
                    console.print(
                        f"[red]{board.company_name}: provider failed ({error_code})[/red]"
                    )

            bulk = run_bulk_ingestion(
                boards,
                repository,
                max_workers=workers,
                progress=report,
            )
            succeeded = len(bulk.succeeded)
            errors.extend(item.error_code for item in bulk.failed)
            failed = bool(bulk.failed)
            console.print(
                f"[cyan]Parallel fetch phase: {bulk.fetch_duration_ms / 1000:.1f}s "
                f"with {workers} workers[/cyan]"
            )
            active_jobs = repository.active_jobs()
            scored_jobs = len(active_jobs)
            for career_profile in profiles:
                if career_profile.profile.slug not in profile_ids:
                    continue
                profile_id = profile_ids[career_profile.profile.slug]
                profile_version = repository.profile_version(profile_id)
                repository.store_matches(
                    profile_id=profile_id,
                    profile_version=profile_version,
                    matches=[
                        (job_id, revision_id, score_job(career_profile, job))
                        for job_id, revision_id, job in active_jobs
                    ],
                )
                console.print(
                    f"[green]{career_profile.profile.display_name} matches refreshed[/green]"
                )
            repository.finish_scan(
                scan_id,
                succeeded=succeeded,
                failed=len(boards) - succeeded,
                scored_jobs=scored_jobs,
                error_codes=errors,
            )
            scan_id = None
    except Exception as exc:
        if scan_id is not None:
            errors.append(type(exc).__name__)
            repository.finish_scan(
                scan_id,
                succeeded=succeeded,
                failed=max(1, len(boards) - succeeded),
                scored_jobs=scored_jobs,
                error_codes=errors,
            )
        raise
    finally:
        repository.close()
    if failed:
        raise click.ClickException("One or more boards failed")


@cli.command("digest")
@click.option(
    "--profile-path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("profiles/adam-cagle.md"),
)
@click.option("--send", "send_message", is_flag=True, help="Send through configured SMTP.")
def digest(profile_path: Path, send_message: bool) -> None:
    """Preview or send a profile's ranked email digest."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise click.ClickException("DATABASE_URL is required")
    career_profile = load_profile(profile_path)
    repository = PostgresRepository(database_url)
    try:
        profile_id = repository.sync_profile(
            career_profile,
            os.environ.get(career_profile.profile.email_env),
        )
        message = compose_digest(
            career_profile.profile.display_name,
            repository.top_matches(
                profile_id,
                minimum_score=career_profile.notifications.minimum_score,
                limit=career_profile.notifications.max_daily_matches,
            ),
        )
    finally:
        repository.close()
    if not send_message:
        console.print(message.text)
        console.print(f"\nIdempotency: {message.idempotency_key}")
        return
    recipient = os.environ.get(career_profile.profile.email_env)
    required = {
        "recipient": recipient,
        "SMTP_FROM": os.environ.get("SMTP_FROM"),
        "SMTP_HOST": os.environ.get("SMTP_HOST"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise click.ClickException(f"Missing email settings: {', '.join(missing)}")
    repository = PostgresRepository(database_url)
    notification_id = repository.claim_notification(
        profile_id=profile_id,
        idempotency_key=message.idempotency_key,
        subject=message.subject,
        payload={"recipient": recipient, "match_count": message.text.count("% match")},
    )
    if notification_id is None:
        repository.close()
        console.print("[yellow]Digest already created for this profile and day[/yellow]")
        return
    try:
        send_smtp(
            message,
            recipient=recipient or "",
            sender=required["SMTP_FROM"] or "",
            host=required["SMTP_HOST"] or "",
            port=int(os.environ.get("SMTP_PORT", "587")),
            username=os.environ.get("SMTP_USERNAME"),
            password=os.environ.get("SMTP_PASSWORD"),
        )
        repository.finish_notification(notification_id, sent=True)
    except Exception as exc:
        repository.finish_notification(
            notification_id,
            sent=False,
            error_code=type(exc).__name__,
        )
        raise click.ClickException("Digest delivery failed") from exc
    finally:
        repository.close()
    console.print(f"[green]Digest sent to {recipient}[/green]")
