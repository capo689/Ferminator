"""Tests for delta computation."""

from anthropic_tracker.delta import compute_delta


class TestComputeDelta:
    def test_first_run_all_added(self, db, sample_jobs):
        result = compute_delta(db, sample_jobs, snapshot_date="2026-04-15")
        assert len(result.added) == 5
        assert len(result.removed) == 0
        assert result.total == 5

    def test_no_changes(self, db, sample_jobs):
        compute_delta(db, sample_jobs, snapshot_date="2026-04-15")
        result = compute_delta(db, sample_jobs, snapshot_date="2026-04-16")
        assert len(result.added) == 0
        assert len(result.removed) == 0
        assert result.unchanged == 5

    def test_job_removed(self, db, sample_jobs):
        compute_delta(db, sample_jobs, snapshot_date="2026-04-15")

        # Remove the last job
        reduced = sample_jobs[:4]
        result = compute_delta(db, reduced, snapshot_date="2026-04-16")
        assert len(result.added) == 0
        assert len(result.removed) == 1
        assert result.removed[0]["id"] == 1005

    def test_job_added(self, db, sample_jobs):
        compute_delta(db, sample_jobs[:3], snapshot_date="2026-04-15")
        result = compute_delta(db, sample_jobs, snapshot_date="2026-04-16")
        assert len(result.added) == 2
        assert result.total == 5

    def test_department_breakdown(self, db, sample_jobs):
        result = compute_delta(db, sample_jobs, snapshot_date="2026-04-15")
        assert result.departments["Software Engineering (Infrastructure)"] == 2
        assert result.departments["Sales"] == 2
        assert result.departments["AI Research & Engineering"] == 1

    def test_location_breakdown(self, db, sample_jobs):
        result = compute_delta(db, sample_jobs, snapshot_date="2026-04-15")
        assert result.locations["San Francisco, CA"] >= 3
        assert "London, UK" in result.locations

    def test_daily_snapshot_written(self, db, sample_jobs):
        compute_delta(db, sample_jobs, snapshot_date="2026-04-15")
        row = db.execute(
            "SELECT * FROM daily_snapshots WHERE date = '2026-04-15'"
        ).fetchone()
        assert row is not None
        assert row["total_active_jobs"] == 5
        assert row["jobs_added"] == 5

    def test_removed_job_marked_inactive(self, db, sample_jobs):
        compute_delta(db, sample_jobs, snapshot_date="2026-04-15")
        compute_delta(db, sample_jobs[:4], snapshot_date="2026-04-16")

        row = db.execute("SELECT * FROM jobs WHERE id = 1005").fetchone()
        assert row["is_active"] == 0
        assert row["removed_date"] == "2026-04-16"

    def test_last_seen_updated(self, db, sample_jobs):
        compute_delta(db, sample_jobs, snapshot_date="2026-04-15")
        compute_delta(db, sample_jobs, snapshot_date="2026-04-16")

        row = db.execute("SELECT * FROM jobs WHERE id = 1001").fetchone()
        assert row["last_seen"] == "2026-04-16"

    def test_empty_jobs_list(self, db):
        result = compute_delta(db, [], snapshot_date="2026-04-15")
        assert result.total == 0
        assert len(result.added) == 0
