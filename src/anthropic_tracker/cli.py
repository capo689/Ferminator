"""CLI entry point for the Anthropic Hiring Tracker."""

import json
import sys

import click
from rich.console import Console

from anthropic_tracker.alerts import evaluate_alerts, show_alerts
from anthropic_tracker.config import get_companies, get_db_path
from anthropic_tracker.dashboard import show_dashboard
from anthropic_tracker.db import get_connection, init_db
from anthropic_tracker.delta import compute_delta
from anthropic_tracker.fetcher import (
    build_department_map,
    enrich_jobs_with_departments,
    fetch_departments,
    fetch_job_details_batch,
    fetch_jobs,
)
from anthropic_tracker.parser import parse_compensation
from anthropic_tracker.summarizer import (
    compensation_report,
    daily_summary,
    delta_summary,
    department_breakdown,
    format_report_csv,
    format_report_json,
    trends_report,
)

console = Console()


@click.group()
@click.option("--db", default=None, help="Path to SQLite database file")
@click.option("--company", default=None,
              help="Greenhouse company slug (default: first in TRACKER_COMPANIES)")
@click.pass_context
def cli(ctx, db, company):
    """Anthropic Hiring Tracker: monitor job openings via the Greenhouse API."""
    ctx.ensure_object(dict)
    companies = get_companies()
    ctx.obj["companies"] = companies
    ctx.obj["company"] = company or companies[0]
    ctx.obj["company_explicit"] = company
    ctx.obj["db_flag"] = db
    try:
        ctx.obj["db_path"] = str(get_db_path(db, ctx.obj["company"]))
    except ValueError as exc:
        raise click.ClickException(str(exc))


@cli.command()
@click.pass_context
def init(ctx):
    """Initialize the database."""
    db_path = ctx.obj["db_path"]
    conn = get_connection(db_path)
    init_db(conn)
    conn.close()
    console.print(f"[green]Database initialized at {db_path}[/green]")


def _fetch_one(company: str, db_path: str, with_salary: bool) -> bool:
    """Fetch, compute deltas, and evaluate alerts for a single company.

    Returns False (after printing the error) on fetch failure, so a
    multi-company loop can keep going instead of aborting.
    """
    conn = get_connection(db_path)
    init_db(conn)

    console.print(f"[dim]Fetching jobs and departments for '{company}'...[/dim]")
    try:
        jobs = fetch_jobs(company)
        depts = fetch_departments(company)
        dept_map = build_department_map(depts)
        jobs = enrich_jobs_with_departments(jobs, dept_map)
    except Exception as exc:
        console.print(f"[red]Failed to fetch jobs for '{company}': {exc}[/red]")
        conn.close()
        return False

    console.print(f"[dim]Got {len(jobs)} jobs for '{company}'. Computing delta...[/dim]")
    result = compute_delta(conn, jobs)

    delta_summary(result.added, result.removed, result.total)

    if with_salary and result.added:
        new_ids = [j["id"] for j in result.added]
        console.print(f"[dim]Fetching salary data for {len(new_ids)} new jobs...[/dim]")
        details = fetch_job_details_batch(company, new_ids)
        salary_count = 0
        for detail in details:
            content = detail.get("content", "")
            if not content:
                continue
            comp = parse_compensation(content)
            if comp:
                conn.execute(
                    """INSERT OR REPLACE INTO compensation
                       (job_id, salary_min, salary_max, currency, comp_type, raw_text)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        detail["id"],
                        comp["salary_min"],
                        comp["salary_max"],
                        comp["currency"],
                        comp["comp_type"],
                        comp["raw_text"],
                    ),
                )
                salary_count += 1
        conn.commit()
        console.print(f"[dim]Parsed salary data for {salary_count}/{len(new_ids)} jobs.[/dim]")

    alerts = evaluate_alerts(conn, result)
    if alerts:
        console.print()
        for alert in alerts:
            color = {"info": "blue", "warning": "yellow", "critical": "red"}.get(
                alert.severity, "white"
            )
            console.print(f"[{color}][ALERT] {alert.message}[/{color}]")

    conn.close()
    return True


@cli.command()
@click.option("--with-salary", is_flag=True, help="Fetch content for salary parsing (slower)")
@click.option("--company", default=None,
              help="Fetch only this company (default: all configured companies)")
@click.pass_context
def fetch(ctx, with_salary, company):
    """Fetch current jobs from Greenhouse API and compute deltas."""
    company = company or ctx.obj.get("company_explicit")
    targets = [company] if company else ctx.obj["companies"]

    if ctx.obj["db_flag"] and len(targets) > 1:
        console.print(
            "[red]Refusing to fetch multiple companies into a single explicit "
            "--db file; pass --company to scope to one company.[/red]"
        )
        sys.exit(1)

    all_ok = True
    for i, slug in enumerate(targets):
        try:
            db_path = str(get_db_path(ctx.obj["db_flag"], slug))
        except ValueError as exc:
            console.print(f"[red]Skipping '{slug}': {exc}[/red]")
            all_ok = False
            if i < len(targets) - 1:
                console.print()
            continue
        all_ok = _fetch_one(slug, db_path, with_salary) and all_ok
        if i < len(targets) - 1:
            console.print()

    if not all_ok:
        sys.exit(1)


@cli.command()
@click.option("--date", default=None, help="Date to summarize (YYYY-MM-DD, default: latest)")
@click.pass_context
def summary(ctx, date):
    """Show summary for a specific date."""
    conn = get_connection(ctx.obj["db_path"])
    daily_summary(conn, date)
    conn.close()


@cli.command()
@click.option(
    "--format", "fmt",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    help="Output format",
)
@click.pass_context
def report(ctx, fmt):
    """Generate a full report of current state."""
    conn = get_connection(ctx.obj["db_path"])

    if fmt == "json":
        data = format_report_json(conn)
        click.echo(json.dumps(data, indent=2, default=str))
    elif fmt == "csv":
        click.echo(format_report_csv(conn))
    else:
        department_breakdown(conn)
        console.print()
        compensation_report(conn)

    conn.close()


@cli.command()
@click.option("--days", default=30, help="Number of days to show")
@click.pass_context
def trends(ctx, days):
    """Show hiring trends over time."""
    conn = get_connection(ctx.obj["db_path"])
    trends_report(conn, days)
    conn.close()


@cli.command()
@click.pass_context
def dashboard(ctx):
    """Launch terminal dashboard."""
    conn = get_connection(ctx.obj["db_path"])
    show_dashboard(conn)
    conn.close()


@cli.command()
@click.option("--all", "show_all", is_flag=True, help="Show all alerts including acknowledged")
@click.pass_context
def alerts(ctx, show_all):
    """Show active alerts."""
    conn = get_connection(ctx.obj["db_path"])
    show_alerts(conn, unacked_only=not show_all)
    conn.close()
