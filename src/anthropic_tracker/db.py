"""SQLite database schema, connection management, and migrations."""

import sqlite3

from anthropic_tracker.config import CURRENT_SCHEMA_VERSION

SCHEMA_SQL = """
-- Reference tables
CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    first_seen DATE NOT NULL,
    last_seen DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS offices (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT,
    first_seen DATE NOT NULL,
    last_seen DATE NOT NULL
);

-- Job lifecycle tracking
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    internal_job_id INTEGER,
    title TEXT NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    location_raw TEXT,
    absolute_url TEXT,
    requisition_id TEXT,
    first_published DATE,
    first_seen DATE NOT NULL,
    last_seen DATE NOT NULL,
    removed_date DATE,
    is_active INTEGER DEFAULT 1
);

-- Many-to-many: jobs can appear in multiple offices
CREATE TABLE IF NOT EXISTS job_offices (
    job_id INTEGER REFERENCES jobs(id),
    office_id INTEGER REFERENCES offices(id),
    PRIMARY KEY (job_id, office_id)
);

-- Many-to-many: jobs can be in multiple departments
CREATE TABLE IF NOT EXISTS job_departments (
    job_id INTEGER REFERENCES jobs(id),
    department_id INTEGER REFERENCES departments(id),
    PRIMARY KEY (job_id, department_id)
);

-- Parsed individual locations from semicolon/pipe-separated strings
CREATE TABLE IF NOT EXISTS job_locations (
    job_id INTEGER REFERENCES jobs(id),
    location_name TEXT NOT NULL,
    PRIMARY KEY (job_id, location_name)
);

-- Compensation data parsed from job HTML
CREATE TABLE IF NOT EXISTS compensation (
    job_id INTEGER PRIMARY KEY REFERENCES jobs(id),
    salary_min INTEGER,
    salary_max INTEGER,
    currency TEXT DEFAULT 'USD',
    comp_type TEXT DEFAULT 'annual',
    raw_text TEXT,
    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Daily snapshots: one row per fetch day
CREATE TABLE IF NOT EXISTS daily_snapshots (
    date DATE PRIMARY KEY,
    total_active_jobs INTEGER NOT NULL,
    jobs_added INTEGER DEFAULT 0,
    jobs_removed INTEGER DEFAULT 0,
    departments_json TEXT,
    locations_json TEXT,
    raw_response_hash TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Weekly rollup metrics
CREATE TABLE IF NOT EXISTS weekly_metrics (
    week_start DATE PRIMARY KEY,
    avg_daily_total REAL,
    total_added INTEGER,
    total_removed INTEGER,
    net_change INTEGER,
    department_changes_json TEXT,
    location_changes_json TEXT,
    comp_median_usd INTEGER,
    notes TEXT
);

-- Alert history
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    alert_type TEXT NOT NULL,
    severity TEXT DEFAULT 'info',
    message TEXT NOT NULL,
    acknowledged INTEGER DEFAULT 0
);

-- Schema versioning
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_jobs_department ON jobs(department_id);
CREATE INDEX IF NOT EXISTS idx_jobs_active ON jobs(is_active);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen);
CREATE INDEX IF NOT EXISTS idx_jobs_removed_date ON jobs(removed_date);
CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_snapshots(date);
CREATE INDEX IF NOT EXISTS idx_compensation_currency ON compensation(currency);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't exist and set schema version."""
    conn.executescript(SCHEMA_SQL)
    # Set schema version if not already set
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] if row[0] is not None else 0
    if current < CURRENT_SCHEMA_VERSION:
        conn.execute(
            "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
            (CURRENT_SCHEMA_VERSION,),
        )
        conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version, or 0 if uninitialized."""
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return row[0] if row[0] is not None else 0
    except sqlite3.OperationalError:
        return 0
