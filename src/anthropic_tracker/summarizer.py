"""Rich-formatted summaries for daily, weekly, and trend reports."""

import json
import sqlite3

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def daily_summary(conn: sqlite3.Connection, target_date: str | None = None) -> None:
    """Print a Rich-formatted summary for a given date's snapshot."""
    console = Console()

    if target_date:
        row = conn.execute(
            "SELECT * FROM daily_snapshots WHERE date = ?", (target_date,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM daily_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()

    if not row:
        console.print("[yellow]No snapshot data found.[/yellow]")
        return

    snap_date = row["date"]
    total = row["total_active_jobs"]
    added = row["jobs_added"]
    removed = row["jobs_removed"]

    # Header
    console.print()
    console.print(Panel(
        f"[bold]Anthropic Hiring Snapshot[/bold]\n{snap_date}",
        style="blue",
    ))

    # Totals
    totals_table = Table(show_header=False, box=None, padding=(0, 2))
    totals_table.add_column(style="bold")
    totals_table.add_column()
    totals_table.add_row("Active Roles", str(total))
    totals_table.add_row("Added", f"[green]+{added}[/green]" if added else "0")
    totals_table.add_row("Removed", f"[red]-{removed}[/red]" if removed else "0")
    console.print(totals_table)
    console.print()

    # Department breakdown
    if row["departments_json"]:
        depts = json.loads(row["departments_json"])
        dept_table = Table(title="By Department", show_lines=False)
        dept_table.add_column("Department", style="cyan")
        dept_table.add_column("Roles", justify="right")
        dept_table.add_column("%", justify="right")
        for name, count in sorted(depts.items(), key=lambda x: x[1], reverse=True):
            pct = f"{count / total * 100:.1f}" if total else "0"
            dept_table.add_row(name, str(count), pct)
        console.print(dept_table)
        console.print()

    # Location breakdown
    if row["locations_json"]:
        locs = json.loads(row["locations_json"])
        loc_table = Table(title="By Location", show_lines=False)
        loc_table.add_column("Location", style="cyan")
        loc_table.add_column("Roles", justify="right")
        for name, count in sorted(locs.items(), key=lambda x: x[1], reverse=True)[:15]:
            loc_table.add_row(name, str(count))
        if len(locs) > 15:
            loc_table.add_row(f"  ... +{len(locs) - 15} more", "")
        console.print(loc_table)


def delta_summary(added: list[dict], removed: list[dict], total: int) -> None:
    """Print a compact delta summary after a fetch."""
    console = Console()
    console.print()

    if not added and not removed:
        console.print(f"[dim]No changes. {total} active roles.[/dim]")
        return

    if added:
        console.print(f"[green]+{len(added)} new roles:[/green]")
        for job in added[:10]:
            console.print(f"  [green]+[/green] {job['title']} ({job['department']})")
        if len(added) > 10:
            console.print(f"  [dim]... +{len(added) - 10} more[/dim]")

    if removed:
        console.print(f"[red]-{len(removed)} removed:[/red]")
        for job in removed[:10]:
            console.print(f"  [red]-[/red] {job['title']} ({job['department']})")
        if len(removed) > 10:
            console.print(f"  [dim]... +{len(removed) - 10} more[/dim]")

    console.print(f"\n[bold]{total}[/bold] active roles total.")


def trends_report(conn: sqlite3.Connection, days: int = 30) -> None:
    """Show rolling trends with sparkline visualization."""
    console = Console()

    rows = conn.execute(
        """SELECT date, total_active_jobs, jobs_added, jobs_removed
           FROM daily_snapshots ORDER BY date DESC LIMIT ?""",
        (days,),
    ).fetchall()

    if not rows:
        msg = "No trend data yet. Run 'tracker fetch' daily to build history."
        console.print(f"[yellow]{msg}[/yellow]")
        return

    rows = list(reversed(rows))  # chronological order

    console.print()
    console.print(Panel("[bold]Anthropic Hiring Trends[/bold]", style="blue"))

    # Sparkline of total roles
    totals = [r["total_active_jobs"] for r in rows]
    sparkline = _sparkline(totals)
    console.print(f"Total roles ({len(rows)}d): {sparkline}")
    console.print(f"  Range: {min(totals)} - {max(totals)}")
    console.print()

    # Daily changes table
    table = Table(title=f"Last {len(rows)} Days", show_lines=False)
    table.add_column("Date", style="dim")
    table.add_column("Total", justify="right")
    table.add_column("Added", justify="right")
    table.add_column("Removed", justify="right")
    table.add_column("Net", justify="right")

    for r in rows[-10:]:  # show last 10
        net = r["jobs_added"] - r["jobs_removed"]
        net_str = f"[green]+{net}[/green]" if net > 0 else f"[red]{net}[/red]" if net < 0 else "0"
        table.add_row(
            r["date"],
            str(r["total_active_jobs"]),
            str(r["jobs_added"]),
            str(r["jobs_removed"]),
            net_str,
        )

    console.print(table)


def department_breakdown(conn: sqlite3.Connection) -> None:
    """Show current active roles grouped by department."""
    console = Console()
    rows = conn.execute(
        """SELECT d.name, COUNT(*) as cnt
           FROM jobs j JOIN departments d ON j.department_id = d.id
           WHERE j.is_active = 1
           GROUP BY d.name ORDER BY cnt DESC"""
    ).fetchall()

    if not rows:
        console.print("[yellow]No active jobs in database.[/yellow]")
        return

    total = sum(r["cnt"] for r in rows)
    table = Table(title="Active Roles by Department")
    table.add_column("Department", style="cyan")
    table.add_column("Roles", justify="right")
    table.add_column("%", justify="right")
    table.add_column("Bar")

    max_count = rows[0]["cnt"] if rows else 1
    for r in rows:
        pct = r["cnt"] / total * 100 if total else 0
        bar_len = int(r["cnt"] / max_count * 30)
        bar = Text("█" * bar_len, style="blue")
        table.add_row(r["name"], str(r["cnt"]), f"{pct:.1f}", bar)

    console.print(table)
    console.print(f"\n[bold]{total}[/bold] total active roles")


def compensation_report(conn: sqlite3.Connection) -> None:
    """Show compensation ranges by department."""
    console = Console()
    rows = conn.execute(
        """SELECT d.name as department,
                  COUNT(*) as cnt,
                  MIN(c.salary_min) as min_sal,
                  MAX(c.salary_max) as max_sal,
                  AVG((c.salary_min + c.salary_max) / 2) as avg_mid,
                  c.currency
           FROM compensation c
           JOIN jobs j ON c.job_id = j.id
           JOIN departments d ON j.department_id = d.id
           WHERE j.is_active = 1
           GROUP BY d.name, c.currency
           ORDER BY avg_mid DESC"""
    ).fetchall()

    if not rows:
        console.print("[yellow]No compensation data. Run 'tracker fetch --with-salary'.[/yellow]")
        return

    table = Table(title="Compensation by Department")
    table.add_column("Department", style="cyan")
    table.add_column("Roles", justify="right")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("Avg Mid", justify="right")
    table.add_column("Currency")

    for r in rows:
        table.add_row(
            r["department"],
            str(r["cnt"]),
            _format_salary(r["min_sal"]),
            _format_salary(r["max_sal"]),
            _format_salary(int(r["avg_mid"])),
            r["currency"],
        )

    console.print(table)


def format_report_json(conn: sqlite3.Connection) -> dict:
    """Generate a full report as a JSON-serializable dict."""
    snap = conn.execute(
        "SELECT * FROM daily_snapshots ORDER BY date DESC LIMIT 1"
    ).fetchone()

    active_jobs = conn.execute(
        """SELECT j.id, j.title, d.name as department, j.location_raw,
                  j.first_published, j.first_seen
           FROM jobs j LEFT JOIN departments d ON j.department_id = d.id
           WHERE j.is_active = 1 ORDER BY d.name, j.title"""
    ).fetchall()

    return {
        "snapshot_date": snap["date"] if snap else None,
        "total_active": snap["total_active_jobs"] if snap else 0,
        "departments": (
            json.loads(snap["departments_json"])
            if snap and snap["departments_json"] else {}
        ),
        "locations": (
            json.loads(snap["locations_json"])
            if snap and snap["locations_json"] else {}
        ),
        "jobs": [dict(row) for row in active_jobs],
    }


def format_report_csv(conn: sqlite3.Connection) -> str:
    """Generate a CSV of all active jobs."""
    rows = conn.execute(
        """SELECT j.id, j.title, d.name as department, j.location_raw,
                  j.first_published, j.first_seen, j.absolute_url
           FROM jobs j LEFT JOIN departments d ON j.department_id = d.id
           WHERE j.is_active = 1 ORDER BY d.name, j.title"""
    ).fetchall()

    lines = ["id,title,department,location,first_published,first_seen,url"]
    for r in rows:
        title = r["title"].replace('"', '""')
        loc = (r["location_raw"] or "").replace('"', '""')
        lines.append(
            f'{r["id"]},"{title}","{r["department"] or ""}","{loc}",'
            f'{r["first_published"] or ""},{r["first_seen"]},{r["absolute_url"] or ""}'
        )
    return "\n".join(lines)


def _sparkline(values: list[int]) -> str:
    """Generate a Unicode sparkline from a list of values."""
    if not values:
        return ""
    blocks = " ▁▂▃▄▅▆▇█"
    lo, hi = min(values), max(values)
    spread = hi - lo or 1
    return "".join(blocks[min(int((v - lo) / spread * 8), 8)] for v in values)


def _format_salary(cents: int) -> str:
    """Format cents as a human-readable salary like $290,000."""
    dollars = cents // 100
    return f"${dollars:,}"
