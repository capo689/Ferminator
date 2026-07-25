"""Rich terminal dashboard for the Anthropic Hiring Tracker."""

import json
import sqlite3

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def show_dashboard(conn: sqlite3.Connection) -> None:
    """Render a full terminal dashboard with current state and trends."""
    console = Console()

    # Gather data
    snap = conn.execute(
        "SELECT * FROM daily_snapshots ORDER BY date DESC LIMIT 1"
    ).fetchone()

    if not snap:
        console.print("[yellow]No data yet. Run 'tracker fetch' first.[/yellow]")
        return

    # Build layout
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=5),
    )
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )

    # Header
    layout["header"].update(Panel(
        f"[bold blue]Anthropic Hiring Tracker[/bold blue]  |  "
        f"{snap['total_active_jobs']} active roles  |  "
        f"Snapshot: {snap['date']}",
        style="blue",
    ))

    # Left: departments
    layout["left"].update(_departments_panel(snap))

    # Right: locations + recent changes
    right_layout = Layout()
    right_layout.split_column(
        Layout(name="locations"),
        Layout(name="changes"),
    )
    right_layout["locations"].update(_locations_panel(snap))
    right_layout["changes"].update(_changes_panel(conn))
    layout["right"].update(right_layout)

    # Footer: alerts
    layout["footer"].update(_alerts_panel(conn))

    console.print(layout)


def _departments_panel(snap) -> Panel:
    """Build department breakdown panel."""
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Department", style="cyan")
    table.add_column("Roles", justify="right")
    table.add_column("", min_width=20)

    depts = json.loads(snap["departments_json"]) if snap["departments_json"] else {}

    sorted_depts = sorted(depts.items(), key=lambda x: x[1], reverse=True)
    max_count = sorted_depts[0][1] if sorted_depts else 1

    for name, count in sorted_depts[:12]:
        bar_len = int(count / max_count * 20)
        bar = Text("█" * bar_len, style="blue")
        table.add_row(name, str(count), bar)

    if len(sorted_depts) > 12:
        table.add_row(f"... +{len(sorted_depts) - 12} more", "", "")

    return Panel(table, title="Departments", border_style="blue")


def _locations_panel(snap) -> Panel:
    """Build location breakdown panel."""
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Location", style="cyan")
    table.add_column("Roles", justify="right")

    locs = json.loads(snap["locations_json"]) if snap["locations_json"] else {}
    sorted_locs = sorted(locs.items(), key=lambda x: x[1], reverse=True)

    for name, count in sorted_locs[:10]:
        table.add_row(name, str(count))

    if len(sorted_locs) > 10:
        table.add_row(f"... +{len(sorted_locs) - 10} more", "")

    return Panel(table, title="Locations", border_style="green")


def _changes_panel(conn: sqlite3.Connection) -> Panel:
    """Build recent daily changes panel."""
    rows = conn.execute(
        """SELECT date, total_active_jobs, jobs_added, jobs_removed
           FROM daily_snapshots ORDER BY date DESC LIMIT 7"""
    ).fetchall()

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Date", style="dim")
    table.add_column("Total", justify="right")
    table.add_column("+", justify="right", style="green")
    table.add_column("-", justify="right", style="red")

    for r in rows:
        table.add_row(
            r["date"],
            str(r["total_active_jobs"]),
            str(r["jobs_added"]) if r["jobs_added"] else "",
            str(r["jobs_removed"]) if r["jobs_removed"] else "",
        )

    return Panel(table, title="Recent Changes (7d)", border_style="yellow")


def _alerts_panel(conn: sqlite3.Connection) -> Panel:
    """Build active alerts panel."""
    rows = conn.execute(
        "SELECT * FROM alerts WHERE acknowledged = 0 ORDER BY triggered_at DESC LIMIT 3"
    ).fetchall()

    if not rows:
        return Panel("[green]No active alerts[/green]", title="Alerts", border_style="green")

    severity_colors = {"info": "blue", "warning": "yellow", "critical": "red"}
    lines = []
    for r in rows:
        color = severity_colors.get(r["severity"], "white")
        lines.append(f"[{color}][{r['severity'].upper()}][/{color}] {r['message']}")

    return Panel("\n".join(lines), title="Alerts", border_style="red")
