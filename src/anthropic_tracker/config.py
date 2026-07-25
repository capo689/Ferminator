"""Configuration constants and paths."""

import os
import re
from pathlib import Path

# HTTP settings
USER_AGENT = "anthropic-tracker/0.1.0 (hiring metrics tracker)"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 2
RETRY_BACKOFF = 1.0  # seconds, doubled each retry
SALARY_FETCH_DELAY = 0.5  # seconds between individual job fetches

# Data storage
DEFAULT_DATA_DIR = Path.home() / ".anthropic-tracker"
DB_FILENAME = "tracker.db"

# Alert thresholds
FREEZE_THRESHOLD_PCT = 20  # total roles drop >20% = possible hiring freeze
SURGE_THRESHOLD_PCT = 50  # department grows >50% in a week
MASS_REMOVAL_THRESHOLD = 30  # >30 roles removed in a single day
SALARY_SHIFT_THRESHOLD_PCT = 10  # median salary changes >10%

# Schema version
CURRENT_SCHEMA_VERSION = 1

DEFAULT_COMPANIES = ["anthropic"]

# Greenhouse slugs are lowercase alphanumerics with optional hyphens/underscores.
# Used to keep company slugs out of filesystem paths in get_db_path().
_VALID_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def get_companies() -> list[str]:
    """Parse TRACKER_COMPANIES into a deduped list of Greenhouse slugs."""
    raw = os.environ.get("TRACKER_COMPANIES", "")
    seen = set()
    companies = []
    for part in raw.split(","):
        slug = part.strip().lower()
        if slug and slug not in seen:
            seen.add(slug)
            companies.append(slug)
    return companies or list(DEFAULT_COMPANIES)


def get_db_path(db_path: str | None = None, company: str | None = None) -> Path:
    """Resolve database file path.

    --db/db_path always wins. Otherwise: one configured company keeps
    today's filename; multiple companies suffix by slug.
    """
    if db_path:
        return Path(db_path)

    companies = get_companies()
    slug = (company or companies[0]).lower()

    env_path = os.environ.get("TRACKER_DB")
    if env_path:
        base = Path(env_path)
        base.parent.mkdir(parents=True, exist_ok=True)
        if len(companies) == 1:
            return base
        if not _VALID_SLUG.match(slug):
            raise ValueError(f"invalid company slug: {slug!r}")
        return base.parent / f"{base.stem}-{slug}{base.suffix}"

    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if len(companies) == 1:
        return DEFAULT_DATA_DIR / DB_FILENAME
    if not _VALID_SLUG.match(slug):
        raise ValueError(f"invalid company slug: {slug!r}")
    stem = Path(DB_FILENAME).stem
    suffix = Path(DB_FILENAME).suffix
    return DEFAULT_DATA_DIR / f"{stem}-{slug}{suffix}"
