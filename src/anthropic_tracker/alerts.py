"""Alert trigger evaluation for hiring metric changes."""

import json
import sqlite3
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from anthropic_tracker.config import (
    FREEZE_THRESHOLD_PCT,
    MASS_REMOVAL_THRESHOLD,
    SURGE_THRESHOLD_PCT,
)
from anthropic_tracker.delta import DeltaResult


@dataclass
class Alert:
    alert_type: str
    severity: str
    message: str


def evaluate_alerts(conn: sqlite3.Connection, delta: DeltaResult) -> list[Alert]:
    """Check all alert conditions and return triggered alerts.

    Also persists triggered alerts to the alerts table.
    """
    triggered = []

    triggered.extend(_check_mass_removal(delta))
    triggered.extend(_check_new_departments(conn, delta))
    triggered.extend(_check_hiring_freeze(conn, delta))
    triggered.extend(_check_department_surge(conn, delta))

    for alert in triggered:
        conn.execute(
            "INSERT INTO alerts (alert_type, severity, message) VALUES (?, ?, ?)",
            (alert.alert_type, alert.severity, alert.message),
        )
    if triggered:
        conn.commit()

    return triggered


def _check_mass_removal(delta: DeltaResult) -> list[Alert]:
    """Trigger if many roles removed in a single day."""
    if len(delta.removed) >= MASS_REMOVAL_THRESHOLD:
        return [Alert(
            alert_type="mass_removal",
            severity="warning",
            message=(
                f"{len(delta.removed)} roles removed in a single fetch "
                f"(threshold: {MASS_REMOVAL_THRESHOLD})"
            ),
        )]
    return []


def _check_new_departments(conn: sqlite3.Connection, delta: DeltaResult) -> list[Alert]:
    """Trigger if a new department appears for the first time."""
    alerts = []
    known = {
        row["name"]
        for row in conn.execute("SELECT DISTINCT name FROM departments").fetchall()
    }
    for dept_name in delta.departments:
        if dept_name not in known and dept_name != "Unknown":
            alerts.append(Alert(
                alert_type="new_department",
                severity="info",
                message=f"New department detected: {dept_name}",
            ))
    return alerts


def _check_hiring_freeze(conn: sqlite3.Connection, delta: DeltaResult) -> list[Alert]:
    """Trigger if total roles dropped significantly vs last week."""
    week_ago = conn.execute(
        """SELECT total_active_jobs FROM daily_snapshots
           WHERE date <= date('now', '-7 days')
           ORDER BY date DESC LIMIT 1"""
    ).fetchone()

    if not week_ago or not week_ago["total_active_jobs"]:
        return []

    prev = week_ago["total_active_jobs"]
    if prev == 0:
        return []

    drop_pct = (prev - delta.total) / prev * 100
    if drop_pct >= FREEZE_THRESHOLD_PCT:
        return [Alert(
            alert_type="hiring_freeze",
            severity="critical",
            message=(
                f"Total roles dropped {drop_pct:.1f}% vs last week "
                f"({prev} -> {delta.total}, threshold: {FREEZE_THRESHOLD_PCT}%)"
            ),
        )]
    return []


def _check_department_surge(conn: sqlite3.Connection, delta: DeltaResult) -> list[Alert]:
    """Trigger if any department grew significantly vs last week."""
    week_ago_snap = conn.execute(
        """SELECT departments_json FROM daily_snapshots
           WHERE date <= date('now', '-7 days')
           ORDER BY date DESC LIMIT 1"""
    ).fetchone()

    if not week_ago_snap or not week_ago_snap["departments_json"]:
        return []

    prev_depts = json.loads(week_ago_snap["departments_json"])
    alerts = []

    for dept_name, current_count in delta.departments.items():
        prev_count = prev_depts.get(dept_name, 0)
        if prev_count == 0:
            continue
        growth_pct = (current_count - prev_count) / prev_count * 100
        if growth_pct >= SURGE_THRESHOLD_PCT:
            alerts.append(Alert(
                alert_type="department_surge",
                severity="warning",
                message=(
                    f"{dept_name} grew {growth_pct:.1f}% vs last week "
                    f"({prev_count} -> {current_count}, threshold: {SURGE_THRESHOLD_PCT}%)"
                ),
            ))

    return alerts


def show_alerts(conn: sqlite3.Connection, unacked_only: bool = True) -> None:
    """Display alerts in a Rich table."""
    console = Console()

    query = "SELECT * FROM alerts"
    if unacked_only:
        query += " WHERE acknowledged = 0"
    query += " ORDER BY triggered_at DESC LIMIT 50"

    rows = conn.execute(query).fetchall()

    if not rows:
        console.print("[green]No active alerts.[/green]")
        return

    table = Table(title="Alerts")
    table.add_column("ID", style="dim")
    table.add_column("Time", style="dim")
    table.add_column("Type")
    table.add_column("Severity")
    table.add_column("Message")

    severity_colors = {"info": "blue", "warning": "yellow", "critical": "red"}

    for r in rows:
        color = severity_colors.get(r["severity"], "white")
        table.add_row(
            str(r["id"]),
            r["triggered_at"],
            r["alert_type"],
            f"[{color}]{r['severity']}[/{color}]",
            r["message"],
        )

    console.print(table)
