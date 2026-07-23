"""FastAPI web dashboard for the Anthropic Hiring Tracker."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from anthropic_tracker.config import get_companies, get_db_path
from anthropic_tracker.db import get_connection, init_db

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

X_COMPANY_HEADER = Header(default=None, alias="X-Company")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize schema once per configured company at startup. Each
    # request opens its own short-lived connection (sqlite is
    # process-shared via WAL).
    for slug in get_companies():
        conn = get_connection(str(get_db_path(None, slug)))
        try:
            init_db(conn)
        finally:
            conn.close()
    yield


app = FastAPI(title="Anthropic Hiring Tracker", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _db(company: str | None = None):
    """Open a fresh database connection and ensure its schema exists."""
    slug = company or get_companies()[0]
    try:
        db_path = str(get_db_path(None, slug))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    conn = get_connection(db_path)
    init_db(conn)
    return conn


def _escape_like(term: str) -> str:
    """Escape SQL LIKE wildcards so user input doesn't act as a pattern."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# --- Pages ---


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, company: str | None = Query(default=None)):
    companies = get_companies()
    slug = company or companies[0]
    conn = _db(slug)
    try:
        snap = conn.execute(
            "SELECT * FROM daily_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        data = _build_dashboard_data(conn, snap)
        data["company"] = slug
        data["companies"] = companies
        return templates.TemplateResponse(request, "dashboard.html", context=data)
    finally:
        conn.close()


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# --- API endpoints ---


@app.get("/api/summary")
async def api_summary(company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        snap = conn.execute(
            "SELECT * FROM daily_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if not snap:
            return {"total": 0, "added": 0, "removed": 0, "date": None}
        return {
            "total": snap["total_active_jobs"],
            "added": snap["jobs_added"],
            "removed": snap["jobs_removed"],
            "date": snap["date"],
        }
    finally:
        conn.close()


@app.get("/api/departments")
async def api_departments(company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT d.name, COUNT(*) as cnt
               FROM jobs j JOIN departments d ON j.department_id = d.id
               WHERE j.is_active = 1
               GROUP BY d.name ORDER BY cnt DESC"""
        ).fetchall()
        total = sum(r["cnt"] for r in rows)
        return {
            "departments": [
                {"name": r["name"], "count": r["cnt"],
                 "pct": round(r["cnt"] / total * 100, 1) if total else 0}
                for r in rows
            ],
            "total": total,
        }
    finally:
        conn.close()


@app.get("/api/locations")
async def api_locations(company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT location_name, COUNT(*) as cnt
               FROM job_locations jl JOIN jobs j ON jl.job_id = j.id
               WHERE j.is_active = 1
               GROUP BY location_name ORDER BY cnt DESC"""
        ).fetchall()
        return {
            "locations": [
                {"name": r["location_name"], "count": r["cnt"]}
                for r in rows
            ]
        }
    finally:
        conn.close()


@app.get("/api/trends")
async def api_trends(days: int = 30, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT date, total_active_jobs, jobs_added, jobs_removed
               FROM daily_snapshots ORDER BY date DESC LIMIT ?""",
            (days,),
        ).fetchall()
        return {
            "days": [
                {
                    "date": r["date"],
                    "total": r["total_active_jobs"],
                    "added": r["jobs_added"],
                    "removed": r["jobs_removed"],
                }
                for r in reversed(rows)
            ]
        }
    finally:
        conn.close()


@app.get("/api/alerts")
async def api_alerts(company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT * FROM alerts WHERE acknowledged = 0
               ORDER BY triggered_at DESC LIMIT 20"""
        ).fetchall()
        return {
            "alerts": [
                {
                    "id": r["id"],
                    "type": r["alert_type"],
                    "severity": r["severity"],
                    "message": r["message"],
                    "time": r["triggered_at"],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


@app.get("/api/search")
async def api_search(q: str = Query(..., min_length=1), company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        terms = [f"%{_escape_like(t.strip())}%" for t in q.split(",") if t.strip()]
        if not terms:
            return {"jobs": [], "query": q}
        clauses = " OR ".join(["j.title LIKE ? ESCAPE '\\'"] * len(terms))
        rows = conn.execute(
            f"""SELECT j.id, j.title, d.name as department,
                       j.absolute_url, j.first_seen
                FROM jobs j
                LEFT JOIN departments d ON j.department_id = d.id
                WHERE j.is_active = 1 AND ({clauses})
                ORDER BY j.first_seen DESC""",
            terms,
        ).fetchall()
        return {
            "jobs": [
                {"id": r["id"], "title": r["title"],
                 "department": r["department"] or "Unknown",
                 "url": r["absolute_url"], "first_seen": r["first_seen"]}
                for r in rows
            ],
            "query": q,
        }
    finally:
        conn.close()


@app.get("/api/recent-changes")
async def api_recent_changes(company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        added = conn.execute(
            """SELECT j.title, d.name as department, j.first_seen, j.absolute_url
               FROM jobs j LEFT JOIN departments d ON j.department_id = d.id
               WHERE j.is_active = 1
               ORDER BY j.first_seen DESC LIMIT 10"""
        ).fetchall()
        removed = conn.execute(
            """SELECT j.title, d.name as department, j.removed_date
               FROM jobs j LEFT JOIN departments d ON j.department_id = d.id
               WHERE j.is_active = 0 AND j.removed_date IS NOT NULL
               ORDER BY j.removed_date DESC LIMIT 10"""
        ).fetchall()
        return {
            "added": [
                {"title": r["title"], "department": r["department"] or "Unknown",
                 "date": r["first_seen"], "url": r["absolute_url"]}
                for r in added
            ],
            "removed": [
                {"title": r["title"], "department": r["department"] or "Unknown",
                 "date": r["removed_date"]}
                for r in removed
            ],
        }
    finally:
        conn.close()


@app.get("/api/compensation")
async def api_compensation(company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
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
        return {
            "compensation": [
                {
                    "department": r["department"],
                    "roles_with_data": r["cnt"],
                    "min": r["min_sal"] // 100 if r["min_sal"] else 0,
                    "max": r["max_sal"] // 100 if r["max_sal"] else 0,
                    "avg_mid": int(r["avg_mid"]) // 100 if r["avg_mid"] else 0,
                    "currency": r["currency"],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


# --- htmx partials ---


@app.get("/partials/summary", response_class=HTMLResponse)
async def partial_summary(request: Request, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        snap = conn.execute(
            "SELECT * FROM daily_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        return templates.TemplateResponse(request, "partials/summary.html", context={
            "snap": snap,
        })
    finally:
        conn.close()


@app.get("/partials/departments", response_class=HTMLResponse)
async def partial_departments(request: Request, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT d.name, COUNT(*) as cnt
               FROM jobs j JOIN departments d ON j.department_id = d.id
               WHERE j.is_active = 1
               GROUP BY d.name ORDER BY cnt DESC"""
        ).fetchall()
        total = sum(r["cnt"] for r in rows)
        max_count = rows[0]["cnt"] if rows else 1
        depts = [
            {"name": r["name"], "count": r["cnt"],
             "pct": round(r["cnt"] / total * 100, 1) if total else 0,
             "bar_width": round(r["cnt"] / max_count * 100)}
            for r in rows
        ]
        return templates.TemplateResponse(request, "partials/departments.html", context={
            "departments": depts,
            "total": total,
        })
    finally:
        conn.close()


@app.get("/partials/locations", response_class=HTMLResponse)
async def partial_locations(request: Request, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT location_name, COUNT(*) as cnt
               FROM job_locations jl JOIN jobs j ON jl.job_id = j.id
               WHERE j.is_active = 1
               GROUP BY location_name ORDER BY cnt DESC"""
        ).fetchall()
        return templates.TemplateResponse(request, "partials/locations.html", context={
            "locations": [{"name": r["location_name"], "count": r["cnt"]} for r in rows],
        })
    finally:
        conn.close()


@app.get("/partials/trends", response_class=HTMLResponse)
async def partial_trends(request: Request, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT date, total_active_jobs, jobs_added, jobs_removed
               FROM daily_snapshots ORDER BY date DESC LIMIT 30"""
        ).fetchall()
        days = list(reversed(rows))
        return templates.TemplateResponse(request, "partials/trends.html", context={
            "days": [
                {"date": r["date"], "total": r["total_active_jobs"],
                 "added": r["jobs_added"], "removed": r["jobs_removed"]}
                for r in days
            ],
        })
    finally:
        conn.close()


@app.get("/partials/alerts", response_class=HTMLResponse)
async def partial_alerts(request: Request, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT * FROM alerts WHERE acknowledged = 0
               ORDER BY triggered_at DESC LIMIT 10"""
        ).fetchall()
        return templates.TemplateResponse(request, "partials/alerts.html", context={
            "alerts": [
                {"type": r["alert_type"], "severity": r["severity"],
                 "message": r["message"], "time": r["triggered_at"]}
                for r in rows
            ],
        })
    finally:
        conn.close()


@app.get("/partials/search", response_class=HTMLResponse)
async def partial_search(
    request: Request,
    q: str = Query("", min_length=0),
    company: str | None = X_COMPANY_HEADER,
):
    if not q.strip():
        return templates.TemplateResponse(request, "partials/search.html", context={
            "jobs": [], "query": "", "empty": True,
        })
    conn = _db(company)
    try:
        terms = [f"%{_escape_like(t.strip())}%" for t in q.split(",") if t.strip()]
        if not terms:
            return templates.TemplateResponse(request, "partials/search.html", context={
                "jobs": [], "query": "", "empty": True,
            })
        clauses = " OR ".join(["j.title LIKE ? ESCAPE '\\'"] * len(terms))
        rows = conn.execute(
            f"""SELECT j.id, j.title, d.name as department,
                       j.absolute_url, j.first_seen
                FROM jobs j
                LEFT JOIN departments d ON j.department_id = d.id
                WHERE j.is_active = 1 AND ({clauses})
                ORDER BY d.name, j.title""",
            terms,
        ).fetchall()
        return templates.TemplateResponse(request, "partials/search.html", context={
            "jobs": [
                {"id": r["id"], "title": r["title"],
                 "department": r["department"] or "Unknown",
                 "url": r["absolute_url"], "first_seen": r["first_seen"]}
                for r in rows
            ],
            "query": q,
            "empty": False,
        })
    finally:
        conn.close()


@app.get("/partials/recent", response_class=HTMLResponse)
async def partial_recent(request: Request, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        added = conn.execute(
            """SELECT j.title, d.name as department, j.first_seen, j.absolute_url
               FROM jobs j LEFT JOIN departments d ON j.department_id = d.id
               WHERE j.is_active = 1
               ORDER BY j.first_seen DESC LIMIT 8"""
        ).fetchall()
        removed = conn.execute(
            """SELECT j.title, d.name as department, j.removed_date
               FROM jobs j LEFT JOIN departments d ON j.department_id = d.id
               WHERE j.is_active = 0 AND j.removed_date IS NOT NULL
               ORDER BY j.removed_date DESC LIMIT 8"""
        ).fetchall()
        return templates.TemplateResponse(request, "partials/recent.html", context={
            "added": [
                {"title": r["title"], "department": r["department"] or "Unknown",
                 "date": r["first_seen"], "url": r["absolute_url"]}
                for r in added
            ],
            "removed": [
                {"title": r["title"], "department": r["department"] or "Unknown",
                 "date": r["removed_date"]}
                for r in removed
            ],
        })
    finally:
        conn.close()


@app.get("/partials/compensation", response_class=HTMLResponse)
async def partial_compensation(request: Request, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
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
        comp = [
            {"department": r["department"], "count": r["cnt"],
             "min": f"${r['min_sal'] // 100:,}" if r["min_sal"] else "N/A",
             "max": f"${r['max_sal'] // 100:,}" if r["max_sal"] else "N/A",
             "avg": f"${int(r['avg_mid']) // 100:,}" if r["avg_mid"] else "N/A",
             "currency": r["currency"]}
            for r in rows
        ]
        return templates.TemplateResponse(request, "partials/compensation.html", context={
            "compensation": comp,
        })
    finally:
        conn.close()


def _build_dashboard_data(conn, snap) -> dict:
    """Build all data needed for the full dashboard render."""
    if not snap:
        return {
            "snap": None, "departments": [], "locations": [],
            "days": [], "alerts": [], "compensation": [],
            "recent_added": [], "recent_removed": [], "total": 0,
        }

    # Departments
    dept_rows = conn.execute(
        """SELECT d.name, COUNT(*) as cnt
           FROM jobs j JOIN departments d ON j.department_id = d.id
           WHERE j.is_active = 1
           GROUP BY d.name ORDER BY cnt DESC"""
    ).fetchall()
    total = sum(r["cnt"] for r in dept_rows)
    max_count = dept_rows[0]["cnt"] if dept_rows else 1
    departments = [
        {"name": r["name"], "count": r["cnt"],
         "pct": round(r["cnt"] / total * 100, 1) if total else 0,
         "bar_width": round(r["cnt"] / max_count * 100)}
        for r in dept_rows
    ]

    # Locations
    loc_rows = conn.execute(
        """SELECT location_name, COUNT(*) as cnt
           FROM job_locations jl JOIN jobs j ON jl.job_id = j.id
           WHERE j.is_active = 1
           GROUP BY location_name ORDER BY cnt DESC"""
    ).fetchall()
    locations = [{"name": r["location_name"], "count": r["cnt"]} for r in loc_rows]

    # Trends
    trend_rows = conn.execute(
        """SELECT date, total_active_jobs, jobs_added, jobs_removed
           FROM daily_snapshots ORDER BY date DESC LIMIT 30"""
    ).fetchall()
    days = [
        {"date": r["date"], "total": r["total_active_jobs"],
         "added": r["jobs_added"], "removed": r["jobs_removed"]}
        for r in reversed(trend_rows)
    ]

    # Alerts
    alert_rows = conn.execute(
        """SELECT * FROM alerts WHERE acknowledged = 0
           ORDER BY triggered_at DESC LIMIT 10"""
    ).fetchall()
    alerts = [
        {"type": r["alert_type"], "severity": r["severity"],
         "message": r["message"], "time": r["triggered_at"]}
        for r in alert_rows
    ]

    # Compensation (raw numbers for charting)
    comp_rows = conn.execute(
        """SELECT d.name as department, COUNT(*) as cnt,
                  MIN(c.salary_min) as min_sal, MAX(c.salary_max) as max_sal,
                  AVG((c.salary_min + c.salary_max) / 2) as avg_mid, c.currency
           FROM compensation c
           JOIN jobs j ON c.job_id = j.id
           JOIN departments d ON j.department_id = d.id
           WHERE j.is_active = 1
           GROUP BY d.name, c.currency ORDER BY avg_mid DESC"""
    ).fetchall()
    compensation = [
        {"department": r["department"], "count": r["cnt"],
         "min": r["min_sal"] // 100 if r["min_sal"] else 0,
         "max": r["max_sal"] // 100 if r["max_sal"] else 0,
         "avg": int(r["avg_mid"]) // 100 if r["avg_mid"] else 0,
         "currency": r["currency"]}
        for r in comp_rows
    ]

    # Recent changes
    added_rows = conn.execute(
        """SELECT j.title, d.name as department, j.first_seen, j.absolute_url
           FROM jobs j LEFT JOIN departments d ON j.department_id = d.id
           WHERE j.is_active = 1
           ORDER BY j.first_seen DESC LIMIT 8"""
    ).fetchall()
    removed_rows = conn.execute(
        """SELECT j.title, d.name as department, j.removed_date
           FROM jobs j LEFT JOIN departments d ON j.department_id = d.id
           WHERE j.is_active = 0 AND j.removed_date IS NOT NULL
           ORDER BY j.removed_date DESC LIMIT 8"""
    ).fetchall()

    return {
        "snap": snap,
        "departments": departments,
        "locations": locations,
        "days": days,
        "alerts": alerts,
        "compensation": compensation,
        "recent_added": [
            {"title": r["title"], "department": r["department"] or "Unknown",
             "date": r["first_seen"], "url": r["absolute_url"]}
            for r in added_rows
        ],
        "recent_removed": [
            {"title": r["title"], "department": r["department"] or "Unknown",
             "date": r["removed_date"]}
            for r in removed_rows
        ],
        "total": total,
    }
