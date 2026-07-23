"""Ferminator command-line interface."""

from __future__ import annotations

import os
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ferminator.adapters import ADAPTERS
from ferminator.domain import ATSProvider, BoardRef
from ferminator.ingestion import run_board_ingestion
from ferminator.profiles import load_profile
from ferminator.registry import load_registry
from ferminator.repository import PostgresRepository

console = Console()


@click.group()
def cli() -> None:
    """Ferminator career intelligence."""


@cli.group()
def profile() -> None:
    """Validate and inspect named career profiles."""


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
    try:
        for board in boards:
            try:
                result = run_board_ingestion(board, repository)
                console.print(
                    f"[green]{board.company_name}[/green] "
                    f"{result.fetched} fetched, {result.added} added, "
                    f"{result.updated} updated, {result.removed} removed, "
                    f"{result.reactivated} reactivated"
                )
            except Exception as exc:
                failed = True
                console.print(f"[red]{board.company_name}: {exc}[/red]")
    finally:
        repository.close()
    if failed:
        raise click.ClickException("One or more boards failed")
