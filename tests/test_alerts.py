"""Tests for alert evaluation."""

import json

from anthropic_tracker.alerts import evaluate_alerts
from anthropic_tracker.delta import DeltaResult


class TestAlerts:
    def test_mass_removal_triggers(self, db):
        delta = DeltaResult(
            removed=[{"id": i, "title": f"Job {i}", "department": "X"} for i in range(35)],
            total=100,
        )
        alerts = evaluate_alerts(db, delta)
        types = [a.alert_type for a in alerts]
        assert "mass_removal" in types

    def test_mass_removal_below_threshold(self, db):
        delta = DeltaResult(
            removed=[{"id": i, "title": f"Job {i}", "department": "X"} for i in range(5)],
            total=100,
        )
        alerts = evaluate_alerts(db, delta)
        types = [a.alert_type for a in alerts]
        assert "mass_removal" not in types

    def test_no_alerts_on_normal_delta(self, db):
        # Pre-populate known departments so new_department doesn't fire
        db.execute(
            "INSERT INTO departments (id, name, first_seen, last_seen) "
            "VALUES (1, 'Engineering', '2026-04-01', '2026-04-15')"
        )
        db.execute(
            "INSERT INTO departments (id, name, first_seen, last_seen) "
            "VALUES (2, 'Sales', '2026-04-01', '2026-04-15')"
        )
        db.commit()

        delta = DeltaResult(
            added=[{"id": 1, "title": "New Job", "department": "Eng"}],
            removed=[],
            total=100,
            departments={"Engineering": 50, "Sales": 50},
        )
        alerts = evaluate_alerts(db, delta)
        assert len(alerts) == 0

    def test_alerts_persisted_to_db(self, db):
        delta = DeltaResult(
            removed=[{"id": i, "title": f"Job {i}", "department": "X"} for i in range(35)],
            total=100,
        )
        evaluate_alerts(db, delta)
        row = db.execute("SELECT COUNT(*) as cnt FROM alerts").fetchone()
        assert row["cnt"] > 0

    def test_hiring_freeze_detection(self, db):
        # Insert a snapshot from 8 days ago with 200 jobs
        db.execute(
            """INSERT INTO daily_snapshots (date, total_active_jobs, jobs_added, jobs_removed)
               VALUES (date('now', '-8 days'), 200, 0, 0)"""
        )
        db.commit()

        # Current delta shows only 150 jobs (25% drop)
        delta = DeltaResult(total=150, departments={"Sales": 150})
        alerts = evaluate_alerts(db, delta)
        types = [a.alert_type for a in alerts]
        assert "hiring_freeze" in types

    def test_department_surge_detection(self, db):
        # Insert a snapshot from 8 days ago
        db.execute(
            """INSERT INTO daily_snapshots
               (date, total_active_jobs, jobs_added, jobs_removed, departments_json)
               VALUES (date('now', '-8 days'), 100, 0, 0, ?)""",
            (json.dumps({"Sales": 20, "Engineering": 80}),),
        )
        db.commit()

        # Sales surged from 20 to 40 (100%)
        delta = DeltaResult(
            total=120,
            departments={"Sales": 40, "Engineering": 80},
        )
        alerts = evaluate_alerts(db, delta)
        types = [a.alert_type for a in alerts]
        assert "department_surge" in types
