"""Ferminator command-line interface."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ferminator.adapters import ADAPTERS
from ferminator.digest import compose_digest, send_smtp
from ferminator.domain import ATSProvider, BoardRef
from ferminator.ingestion import run_board_ingestion
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
@click.option(
    "--path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("config/companies.yaml"),
)
def registry_validate(path: Path) -> None:
    """Validate the curated company registry."""
    registry = load_registry(path)
    table = Table("Company", "Provider", "Board", "Status")
    for company in registry.companies:
        for board in company.boards:
            status = "enabled" if company.enabled and board.enabled else "disabled"
            table.add_row(company.name, board.provider.value, board.board_key, status)
    console.print(table)


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


@cli.command("scan")
@click.option(
    "--registry",
    "registry_path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("config/companies.yaml"),
)
@click.option("--provider", type=click.Choice([item.value for item in ATSProvider]))
@click.option("--company")
def scan(registry_path: Path, provider: str | None, company: str | None) -> None:
    """Ingest enabled public boards into Postgres."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise click.ClickException("DATABASE_URL is required")
    registry = load_registry(registry_path)
    boards = registry.enabled_boards
    if provider:
        boards = [board for board in boards if board.provider.value == provider]
    if company:
        boards = [board for board in boards if board.company_slug == company]
    if not boards:
        raise click.ClickException("No enabled boards match the filters")
    repository = PostgresRepository(database_url)
    failed = False
    succeeded = 0
    errors: list[str] = []
    scored_jobs = 0
    scan_identity = (
        f"{datetime.now(UTC).strftime('%Y%m%d%H')}:"
        f"{provider or 'all'}:{company or 'all'}"
    )
    scan_key = hashlib.sha256(scan_identity.encode()).hexdigest()
    scan_id: str | None = None
    try:
        with repository.scan_lock():
            scan_id = repository.start_scan(scan_key, len(boards))
            profiles = [load_profile(path) for path in sorted(Path("profiles").glob("*.md"))]
            profile_ids = {
                profile.profile.slug: repository.sync_profile(
                    profile,
                    os.environ.get(profile.profile.email_env),
                )
                for profile in profiles
                if profile.search.enabled
            }
            for board in boards:
                try:
                    result = run_board_ingestion(board, repository)
                    succeeded += 1
                    console.print(
                        f"[green]{board.company_name}[/green] "
                        f"{result.fetched} fetched, {result.added} added, "
                        f"{result.updated} updated, {result.removed} removed, "
                        f"{result.reactivated} reactivated"
                    )
                except Exception as exc:
                    failed = True
                    error_code = getattr(exc, "code", type(exc).__name__)
                    errors.append(str(error_code))
                    console.print(
                        f"[red]{board.company_name}: provider failed "
                        f"({error_code})[/red]"
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
