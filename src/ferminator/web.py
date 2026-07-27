"""Ferminator web application."""

from __future__ import annotations

import logging
import time
from collections import Counter, defaultdict, deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from ferminator import __version__
from ferminator.auth import (
    AuthenticationError,
    SupabaseAuthClient,
    current_user_id,
    save_session,
)
from ferminator.demo import demo_companies, demo_pipeline, scored_jobs
from ferminator.discover_visibility import apply_role_thresholds, sort_discover_matches
from ferminator.display_score import match_display
from ferminator.domain import extract_compensation_from_text, html_to_text
from ferminator.feedback import WRONG_REASON_LABELS, render_calibration_markdown
from ferminator.freshness import annotate_freshness, apply_default_freshness_policy
from ferminator.geography import (
    is_remote_job,
    job_distance_miles,
    location_category,
    lookup_zip,
)
from ferminator.matching import matched_role_family
from ferminator.observability import configure_logging, safe_request_id
from ferminator.profiles import CareerProfile, load_profile, parse_profile_markdown
from ferminator.repository import PostgresRepository
from ferminator.settings import get_settings

PACKAGE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
logger = logging.getLogger("ferminator.web")
_failed_auth: dict[str, deque[float]] = defaultdict(deque)
_AUTH_WINDOW_SECONDS = 300
_AUTH_MAX_FAILURES = 5


def _security_headers(response: Response, request_id: str) -> Response:
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response


def _alpha_password(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Basic "):
        return ""
    import base64
    import binascii

    try:
        decoded = base64.b64decode(authorization[6:], validate=True).decode()
        _, password = decoded.split(":", 1)
        return password
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return ""


def _auth_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.validate_runtime()
    load_profile(settings.profile_path)
    database_host = urlsplit(settings.database_url).hostname if settings.database_url else None
    logger.info(
        "application_started",
        extra={
            "event": "startup",
            "dependency": f"postgres:{database_host}" if database_host else "demo",
        },
    )
    yield
    logger.info("application_stopped", extra={"event": "shutdown"})


app = FastAPI(
    title="Ferminator Career Intelligence",
    version=__version__,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = safe_request_id(request.headers.get("x-request-id"))
    request.state.request_id = request_id
    started = time.perf_counter()
    settings = get_settings()
    public_path = request.url.path in {"/healthz", "/readyz"} or request.url.path.startswith(
        "/static/"
    )
    if settings.auth_mode == "shared_password" and not public_path:
        key = _auth_key(request)
        attempts = _failed_auth[key]
        cutoff = time.monotonic() - _AUTH_WINDOW_SECONDS
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        if len(attempts) >= _AUTH_MAX_FAILURES:
            response = Response(status_code=429, headers={"Retry-After": "300"})
            logger.warning(
                "authentication_rate_limited",
                extra={
                    "event": "authentication_rate_limited",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 429,
                },
            )
            return _security_headers(response, request_id)
        if not settings.valid_alpha_password(_alpha_password(request)):
            attempts.append(time.monotonic())
            response = Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Ferminator private alpha"'},
            )
            logger.warning(
                "authentication_failed",
                extra={
                    "event": "authentication_failed",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 401,
                },
            )
            return _security_headers(response, request_id)
        attempts.clear()
    if settings.auth_mode == "supabase" and not public_path:
        if request.method not in {"GET", "HEAD", "OPTIONS"} and settings.is_production:
            expected_origin = settings.public_base_url.rstrip("/")
            if request.headers.get("origin", "").rstrip("/") != expected_origin:
                response = Response(status_code=403)
                return _security_headers(response, request_id)
        if request.url.path not in {"/login", "/set-password"}:
            auth_client = SupabaseAuthClient(settings)
            user_id = await current_user_id(request, auth_client)
            if not user_id:
                target = quote(str(request.url.path))
                response = RedirectResponse(f"/login?next={target}", status_code=303)
                return _security_headers(response, request_id)
            repository = _repository()
            try:
                account = repository.account_for_user(user_id)
            finally:
                repository.close()
            if not account or account.status != "active":
                request.session.clear()
                response = HTMLResponse("Account unavailable.", status_code=403)
                return _security_headers(response, request_id)
            request.state.account = account
            if request.url.path.startswith("/admin") and account.role != "sysadmin":
                response = HTMLResponse("Administrator access required.", status_code=403)
                return _security_headers(response, request_id)
            if account.role == "sysadmin" and not request.url.path.startswith(
                ("/admin", "/logout")
            ):
                response = RedirectResponse("/admin", status_code=303)
                return _security_headers(response, request_id)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed",
            extra={
                "event": "request_failed",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        raise
    _security_headers(response, request_id)
    logger.info(
        "request_complete",
        extra={
            "request_id": request_id,
            "event": "request_complete",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return response


app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().session_secret or "ferminator-development-session-secret",
    session_cookie="ferminator_session",
    max_age=60 * 60 * 24 * 7,
    same_site="lax",
    https_only=get_settings().is_production,
)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", safe_request_id(None))
    logger.exception(
        "unhandled_exception",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={
            "event": "unhandled_exception",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": 500,
        },
    )
    return HTMLResponse(
        (
            "<!doctype html><html><head><title>Ferminator needs a moment</title></head>"
            "<body><main><h1>We hit a snag.</h1>"
            "<p>The error has been logged. Try again in a moment.</p>"
            f"<p>Support code: <code>{request_id}</code></p></main></body></html>"
        ),
        status_code=500,
        headers={"X-Request-ID": request_id},
    )


def _profile(request: Request | None = None) -> CareerProfile:
    if request is not None and get_settings().auth_mode == "supabase":
        account = getattr(request.state, "account", None)
        if account is None or account.role != "user":
            raise HTTPException(status_code=403, detail="A user profile is required")
        repository = _repository()
        try:
            return repository.profile_for_account(account.id)
        finally:
            repository.close()
    return load_profile(get_settings().profile_path)


def _context(request: Request, active: str) -> dict:
    profile = _profile(request)
    return {
        "request": request,
        "active": active,
        "profile": profile,
        "display_name": profile.profile.display_name,
        "demo_mode": get_settings().demo_mode,
        "version": __version__,
        "authenticated": get_settings().auth_mode == "supabase",
    }


def _repository() -> PostgresRepository:
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for live dashboard data")
    return PostgresRepository(database_url, min_size=1, max_size=2)


def _apply_role_thresholds(
    profile: CareerProfile,
    matches: list[dict],
    overrides: dict[str, int],
) -> list[dict]:
    """Annotate and filter matches using each role family's visibility floor."""
    return [
        _apply_visible_compensation(item)
        for item in apply_role_thresholds(profile, matches, overrides)
    ]


def _apply_visible_compensation(item: dict) -> dict:
    """Extract JD pay only after a role has passed the user's visibility rules."""
    compensation_text = item.pop("compensation_text", None)
    if item.get("compensation") or not compensation_text:
        return item
    inferred = extract_compensation_from_text(compensation_text)
    if inferred is None or inferred.minimum is None:
        return item
    upper = inferred.maximum or inferred.minimum
    symbol = (
        "$"
        if inferred.currency in {None, "USD"}
        else {"GBP": "£", "EUR": "€"}.get(inferred.currency, inferred.currency)
    )
    if inferred.interval == "hour":
        label = f"{symbol}{inferred.minimum:,.0f}–{symbol}{upper:,.0f}/hour"
    else:
        label = f"{symbol}{inferred.minimum / 1000:,.0f}K–{symbol}{upper / 1000:,.0f}K"
    return {
        **item,
        "compensation": label,
        "compensation_source": "description",
        "compensation_minimum": inferred.minimum,
        "compensation_maximum": upper,
        "compensation_currency": inferred.currency,
        "compensation_interval": inferred.interval,
        "concerns": [
            concern
            for concern in item.get("concerns", [])
            if "compensation is not disclosed" not in concern.casefold()
        ],
    }


def _matches(profile: CareerProfile, *, minimum_score: float = 0) -> list[dict]:
    if get_settings().demo_mode:
        return _apply_role_thresholds(
            profile,
            [item for item in scored_jobs(profile) if item["score"] >= minimum_score],
            {},
        )
    repository = _repository()
    try:
        matches = repository.web_matches(
            profile.profile.slug,
            minimum_score=minimum_score,
            limit=5000,
        )
        overrides = repository.role_thresholds(profile.profile.slug)
        return _apply_role_thresholds(profile, matches, overrides)
    finally:
        repository.close()


def _compile_intelligence(
    profile: CareerProfile,
    matches: list[dict],
    market_data: dict,
    source_health: dict,
    quality: dict,
    overrides: dict[str, int],
) -> dict:
    """Build an honest, explainable snapshot from current production facts."""
    overview = market_data["overview"]
    visible_count = len(matches)
    strong_count = sum(item["score"] >= profile.notifications.minimum_score for item in matches)
    exceptional_count = sum(
        item["score"] >= profile.notifications.exceptional_score for item in matches
    )
    remote_count = sum(item["workplace"] == "remote" for item in matches)
    remote_rate = round(100 * remote_count / visible_count) if visible_count else 0

    annual_salaries = [
        (item["compensation_minimum"] + item["compensation_maximum"]) / 2
        for item in matches
        if item.get("compensation_minimum") is not None
        and item.get("compensation_maximum") is not None
        and item.get("compensation_currency") in {None, "USD"}
        and item.get("compensation_interval") in {None, "year", "annual", "annually"}
    ]
    median_salary = round(median(annual_salaries) / 1000) if annual_salaries else None
    salary_coverage = round(100 * len(annual_salaries) / visible_count) if visible_count else 0

    family_data: dict[str, dict] = {}
    skill_counts: Counter[str] = Counter()
    skill_score_totals: Counter[str] = Counter()
    provider_visible: Counter[str] = Counter()
    for item in matches:
        provider_visible[item["provider"]] += 1
        family_id = item["role_family_id"]
        family = family_data.setdefault(
            family_id,
            {
                "id": family_id,
                "label": item["role_family"],
                "threshold": item["role_threshold"],
                "count": 0,
                "scores": [],
                "remote": 0,
                "salaries": [],
            },
        )
        family["count"] += 1
        family["scores"].append(float(item["score"]))
        family["remote"] += item["workplace"] == "remote"
        if (
            item.get("compensation_minimum") is not None
            and item.get("compensation_maximum") is not None
            and item.get("compensation_currency") in {None, "USD"}
            and item.get("compensation_interval")
            in {
                None,
                "year",
                "annual",
                "annually",
            }
        ):
            family["salaries"].append(
                (item["compensation_minimum"] + item["compensation_maximum"]) / 2
            )
        job_skills = {
            evidence.split(":", 1)[1].strip()
            for evidence in item.get("evidence", [])
            if evidence.startswith("Preferred evidence:")
        }
        for skill in job_skills:
            skill_counts[skill] += 1
            skill_score_totals[skill] += float(item["score"])

    role_families = []
    for family in family_data.values():
        role_families.append(
            {
                "id": family["id"],
                "label": family["label"],
                "count": family["count"],
                "average_score": round(sum(family["scores"]) / family["count"], 1),
                "maximum_score": round(max(family["scores"]), 1),
                "remote_rate": round(100 * family["remote"] / family["count"]),
                "median_salary": (
                    round(median(family["salaries"]) / 1000) if family["salaries"] else None
                ),
                "threshold": family["threshold"],
            }
        )
    role_families.sort(
        key=lambda item: (item["maximum_score"], item["count"]),
        reverse=True,
    )

    skills = [
        {
            "label": skill,
            "count": count,
            "share": round(100 * count / visible_count) if visible_count else 0,
            "average_score": round(skill_score_totals[skill] / count, 1),
        }
        for skill, count in skill_counts.most_common(8)
    ]

    providers = []
    for row in market_data["providers"]:
        active = int(row["active_jobs"])
        eligible = int(row["eligible_jobs"])
        provider = str(row["provider"])
        providers.append(
            {
                "provider": provider,
                "boards": int(row["board_count"]),
                "active_jobs": active,
                "eligible_jobs": eligible,
                "visible_jobs": provider_visible[provider],
                "strong_jobs": int(row["strong_jobs"]),
                "yield": round(1000 * eligible / active, 1) if active else 0,
            }
        )

    boards = source_health.get("boards", [])
    source_exceptions = [board for board in boards if board["validation_status"] != "healthy"]
    latest_scan = source_health.get("latest_scan")
    scan_minutes = None
    if latest_scan and latest_scan.get("finished_at"):
        scan_minutes = round(
            (latest_scan["finished_at"] - latest_scan["started_at"]).total_seconds() / 60,
            1,
        )

    observed_since = overview.get("observed_since")
    observed_days = max(0, (datetime.now(UTC) - observed_since).days) if observed_since else 0
    trend_ready = observed_days >= 14
    active_jobs = int(overview["active_jobs"])
    raw_eligible = int(overview["eligible_jobs"])
    relevant_yield = round(100 * raw_eligible / active_jobs, 2) if active_jobs else 0
    maximum_score = float(overview["maximum_score"] or 0)
    leader = next((item for item in providers if item["strong_jobs"]), None)

    insights = [
        {
            "title": "Your market is selective.",
            "body": (
                f"{raw_eligible:,} of {active_jobs:,} active jobs passed the matcher "
                f"({relevant_yield}%). Coverage is broad; relevance is intentionally narrow."
            ),
        },
        {
            "title": "Remote supply is not the bottleneck.",
            "body": (
                f"{remote_count} of {visible_count} visible opportunities are remote "
                f"({remote_rate}%). Role quality and calibration matter more than location."
            ),
        },
    ]
    if maximum_score < 80:
        insights.append(
            {
                "title": "The scoring ceiling is still compressed.",
                "body": (
                    f"The current best score is {maximum_score:g}. Calibration V1 contains "
                    "credible 80–96 opportunities, so current scores should rank jobs—not "
                    "be treated as final apply probabilities."
                ),
            }
        )
    if leader:
        insights.append(
            {
                "title": f"{leader['provider'].title()} is producing the strongest volume.",
                "body": (
                    f"It currently contributes {leader['strong_jobs']} of "
                    f"{strong_count} visible jobs scoring "
                    f"{profile.notifications.minimum_score}+."
                ),
            }
        )

    return {
        "generated_at": datetime.now(UTC),
        "cards": [
            {
                "label": "Market searched",
                "value": f"{active_jobs:,}",
                "note": f"Across {len(boards):,} enabled company boards",
            },
            {
                "label": "Visible opportunities",
                "value": f"{visible_count:,}",
                "note": f"{relevant_yield}% of the active market",
            },
            {
                "label": f"Score {profile.notifications.minimum_score}+",
                "value": f"{strong_count:,}",
                "note": f"{exceptional_count} at {profile.notifications.exceptional_score}+",
            },
            {
                "label": "Remote share",
                "value": f"{remote_rate}%",
                "note": f"{remote_count} visible remote roles",
            },
            {
                "label": "Median visible pay",
                "value": f"${median_salary}K" if median_salary else "Building",
                "note": f"{salary_coverage}% salary coverage",
            },
            {
                "label": "Current score ceiling",
                "value": f"{maximum_score:g}",
                "note": "Ranking signal, not application probability",
            },
        ],
        "funnel": [
            {"label": "Active jobs scanned", "value": active_jobs},
            {"label": "Matcher eligible", "value": raw_eligible},
            {"label": "Visible after role rules", "value": visible_count},
            {"label": f"Score {profile.notifications.minimum_score}+", "value": strong_count},
            {"label": "Saved in Ferminator", "value": int(overview["saved_jobs"])},
            {"label": "Applied in Ferminator", "value": int(overview["tracked_applications"])},
            {"label": "Interviewing or offer", "value": int(overview["active_responses"])},
        ],
        "historical_applications": int(overview["historical_applications"]),
        "role_families": role_families,
        "skills": skills,
        "providers": providers,
        "quality": quality,
        "source_summary": {
            "healthy": len(boards) - len(source_exceptions),
            "total": len(boards),
            "exceptions": source_exceptions,
            "latest_scan": latest_scan,
            "scan_minutes": scan_minutes,
        },
        "baseline": {
            "observed_days": observed_days,
            "trend_ready": trend_ready,
            "new_jobs_24h": int(overview["new_jobs_24h"]),
            "removed_jobs_7d": int(overview["removed_jobs_7d"]),
        },
        "thresholds_wide_open": bool(overrides)
        and all(threshold == 0 for threshold in overrides.values()),
        "exclusions": market_data["exclusions"],
        "insights": insights,
    }


def _reset_token_hash(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@app.get("/set-password", response_class=HTMLResponse)
def set_password_page(request: Request, token: str = Query(default="")):
    """Single-use page for setting a new password.

    Exists because there was no recovery path at all: a user who lost their
    password had to be reset by hand in the database.
    """
    if get_settings().auth_mode != "supabase":
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "set_password.html",
        context={"request": request, "token": token, "error": None, "done": False},
    )


@app.post("/set-password", response_class=HTMLResponse)
async def set_password(request: Request):
    if get_settings().auth_mode != "supabase":
        return RedirectResponse("/", status_code=303)
    fields = await _form_fields(request)
    token = fields.get("token", "")
    password = fields.get("password", "")
    confirm = fields.get("confirm", "")

    def fail(message: str, status: int = 400):
        return templates.TemplateResponse(
            request,
            "set_password.html",
            context={"request": request, "token": token, "error": message, "done": False},
            status_code=status,
        )

    if len(password) < 12:
        return fail("Use at least 12 characters.")
    if password != confirm:
        return fail("The two passwords do not match.")

    repository = _repository()
    try:
        claim = repository.claim_password_reset_token(_reset_token_hash(token))
    finally:
        repository.close()
    if not claim:
        return fail("That link is invalid, already used, or expired.", status=403)

    auth_client = SupabaseAuthClient(get_settings())
    try:
        await auth_client.set_user_password(str(claim["auth_user_id"]), password)
    except RuntimeError:
        logger.exception("password_set_failed", extra={"event": "password_set_failed"})
        return fail("Could not update the password. Try the link again.", status=500)

    logger.info(
        "password_set",
        extra={"event": "password_set", "username": claim["username"]},
    )
    return templates.TemplateResponse(
        request,
        "set_password.html",
        context={
            "request": request,
            "token": "",
            "error": None,
            "done": True,
            "username": claim["username"],
        },
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = Query(default="/")):
    if get_settings().auth_mode != "supabase":
        return RedirectResponse("/", status_code=303)
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/"
    return templates.TemplateResponse(
        request,
        "login.html",
        context={"request": request, "next": safe_next, "error": None},
    )


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request):
    raw = (await request.body()).decode("utf-8", errors="replace")
    fields = {key: values[-1] for key, values in parse_qs(raw).items()}
    username = fields.get("username", "").strip()
    password = fields.get("password", "")
    safe_next = fields.get("next", "/")
    if not safe_next.startswith("/") or safe_next.startswith("//"):
        safe_next = "/"
    key = _auth_key(request)
    attempts = _failed_auth[key]
    cutoff = time.monotonic() - _AUTH_WINDOW_SECONDS
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    if len(attempts) >= _AUTH_MAX_FAILURES:
        return templates.TemplateResponse(
            request,
            "login.html",
            context={
                "request": request,
                "next": safe_next,
                "error": "Too many attempts. Try again in five minutes.",
            },
            status_code=429,
            headers={"Retry-After": "300"},
        )
    repository = _repository()
    try:
        email = repository.login_email_for_username(username)
    finally:
        repository.close()
    try:
        if not email:
            raise AuthenticationError("The username or password was not recognized.")
        tokens = await SupabaseAuthClient(get_settings()).sign_in(email, password)
        repository = _repository()
        try:
            account = repository.account_for_user(tokens.user_id)
            if not account or account.status != "active":
                raise AuthenticationError("The username or password was not recognized.")
            repository.record_login(account.id)
        finally:
            repository.close()
    except AuthenticationError as exc:
        attempts.append(time.monotonic())
        return templates.TemplateResponse(
            request,
            "login.html",
            context={"request": request, "next": safe_next, "error": str(exc)},
            status_code=401,
        )
    attempts.clear()
    save_session(request, tokens)
    destination = "/admin" if account.role == "sysadmin" else safe_next
    return RedirectResponse(destination, status_code=303)


@app.post("/logout")
async def logout(request: Request):
    access_token = request.session.get("access_token")
    if access_token:
        await SupabaseAuthClient(get_settings()).sign_out(str(access_token))
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, created: bool = Query(default=False)):
    repository = _repository()
    try:
        accounts = repository.admin_accounts()
        directory = repository.company_directory("adam-cagle")
    finally:
        repository.close()
    return templates.TemplateResponse(
        request,
        "admin.html",
        context={
            "request": request,
            "accounts": accounts,
            "directory": directory,
            "created": created,
            "error": None,
            "version": __version__,
        },
    )


@app.post("/admin/accounts", response_class=HTMLResponse)
async def admin_create_account(request: Request):
    form = await request.form()
    username = str(form.get("username", "")).strip()
    email = str(form.get("email", "")).strip().casefold()
    password = str(form.get("password", ""))
    timezone = str(form.get("timezone", "America/Los_Angeles"))
    run_times = [
        value
        for value in (
            str(form.get("run_time_1", "")).strip(),
            str(form.get("run_time_2", "")).strip(),
        )
        if value
    ]
    profile_file = form.get("profile")
    error = None
    raw_profile = ""
    if not username or not email or len(password) < 12 or not run_times:
        error = "Username, email, a 12+ character password, and a run time are required."
    elif not hasattr(profile_file, "read"):
        error = "Attach the completed Ferminator onboarding Markdown file."
    else:
        content = await profile_file.read()
        if len(content) > 2_000_000:
            error = "The profile file is larger than 2 MB."
        else:
            try:
                raw_profile = content.decode("utf-8")
                profile = parse_profile_markdown(
                    raw_profile,
                    source_path=f"upload://{getattr(profile_file, 'filename', 'profile.md')}",
                )
            except (UnicodeDecodeError, ValueError) as exc:
                error = f"The profile could not be validated: {exc}"
    auth_user_id = None
    if error is None:
        auth_client = SupabaseAuthClient(get_settings())
        try:
            auth_user_id = await auth_client.create_user(
                email=email,
                password=password,
                username=username,
            )
            repository = _repository()
            try:
                repository.provision_user_account(
                    auth_user_id=auth_user_id,
                    username=username,
                    email=email,
                    profile=profile,
                    onboarding_markdown=raw_profile,
                    timezone=timezone,
                    run_times=run_times,
                    actor_account_id=request.state.account.id,
                    request_id=request.state.request_id,
                )
            finally:
                repository.close()
        except Exception:
            logger.exception(
                "account_provisioning_failed",
                extra={
                    "event": "account_provisioning_failed",
                    "request_id": request.state.request_id,
                },
            )
            if auth_user_id:
                await auth_client.delete_user(auth_user_id)
            error = "Account setup failed safely; no partial Ferminator account was kept."
    if error is None:
        return RedirectResponse("/admin?created=true", status_code=303)
    repository = _repository()
    try:
        accounts = repository.admin_accounts()
        directory = repository.company_directory("adam-cagle")
    finally:
        repository.close()
    return templates.TemplateResponse(
        request,
        "admin.html",
        context={
            "request": request,
            "accounts": accounts,
            "directory": directory,
            "created": False,
            "error": error,
            "version": __version__,
        },
        status_code=400,
    )


@app.get("/", response_class=HTMLResponse)
def today(request: Request):
    context = _context(request, "today")
    matches = _matches(context["profile"])
    context.update(
        {
            "matches": matches,
            "review_matches": [],
            "lead": matches[0] if matches else None,
            "secondary": matches[1:],
            "stats": {
                "new_matches": len(matches),
                "review_matches": 0,
                "exceptional": sum(
                    item["score"] >= context["profile"].notifications.exceptional_score
                    for item in matches
                ),
                "changed": 2,
                "followups": 1,
            },
        }
    )
    return templates.TemplateResponse(request, "today.html", context=context)


@app.get("/discover", response_class=HTMLResponse)
def discover(
    request: Request,
    q: str = Query(default=""),
    sort: str = Query(default="relevance"),
    posted: str = Query(default="anytime"),
    location_mode: str | None = Query(default=None),
    zip_code: str | None = Query(default=None, alias="zip"),
    radius: int | None = Query(default=None),
    min_score: int | None = Query(default=None, ge=0, le=100),
    show_rejected: bool = Query(default=False),
):
    context = _context(request, "discover")
    profile = context["profile"]
    rules = profile.search
    sort = sort if sort in {"relevance", "newest"} else "relevance"
    posted = posted if posted in {"anytime", "30d", "7d", "24h"} else "anytime"
    location_mode = location_mode or rules.default_location_mode
    if location_mode not in {"remote", "near", "remote_or_near", "anywhere"}:
        location_mode = rules.default_location_mode
    zip_code = (zip_code or rules.default_zip).strip()
    radius = radius if radius in {10, 25, 50, 100} else rules.default_radius_miles
    origin = lookup_zip(zip_code)
    zip_error = None if origin else "Enter a valid five-digit US ZIP code."
    effective_minimum = min_score or 0

    matches = annotate_freshness(_matches(profile, minimum_score=0))
    if not show_rejected:
        matches = [
            item for item in matches if item.get("feedback_verdict") not in {"wrong", "duplicate"}
        ]
        matches = apply_default_freshness_policy(matches)
    for item in matches:
        display = match_display(item["score"])
        item.update(
            {
                "display_score": display.score,
                "display_label": display.label,
                "display_band": display.band,
            }
        )
    if q:
        needle = q.casefold()
        matches = [
            item
            for item in matches
            if needle in f"{item['title']} {item['company']} {item['department']}".casefold()
        ]
    if effective_minimum:
        matches = [item for item in matches if item["display_score"] >= effective_minimum]
    if posted != "anytime":
        window = {"30d": timedelta(days=30), "7d": timedelta(days=7), "24h": timedelta(hours=24)}
        cutoff = datetime.now(UTC) - window[posted]
        matches = [
            item
            for item in matches
            if item["freshness_effective_at"] >= cutoff
        ]
    for item in matches:
        distance = job_distance_miles(item, origin) if origin else None
        category, category_label = location_category(item, distance, radius)
        item.update(
            {
                "distance_miles": round(distance) if distance is not None else None,
                "location_category": category,
                "location_category_label": category_label,
            }
        )
    if location_mode != "anywhere":
        matches = [
            item
            for item in matches
            if (
                location_mode == "remote"
                and is_remote_job(item)
                or location_mode == "near"
                and item["distance_miles"] is not None
                and item["distance_miles"] <= radius
                or location_mode == "remote_or_near"
                and (
                    is_remote_job(item)
                    or item["distance_miles"] is not None
                    and item["distance_miles"] <= radius
                )
            )
        ]

    matches = sort_discover_matches(matches, sort)

    params = {
        "q": q,
        "sort": sort,
        "posted": posted,
        "location_mode": location_mode,
        "zip": zip_code,
        "radius": radius,
        "min_score": effective_minimum,
        "show_rejected": show_rejected,
    }
    chips = []
    labels = {
        "30d": "Last 30 days",
        "7d": "Last 7 days",
        "24h": "Last 24 hours",
        "remote": "Remote",
        "near": f"Within {radius} mi of {zip_code}",
        "remote_or_near": f"Remote or within {radius} mi",
    }
    defaults = {
        "q": "",
        "sort": "relevance",
        "posted": "anytime",
        "location_mode": rules.default_location_mode,
        "zip": rules.default_zip,
        "radius": rules.default_radius_miles,
        "min_score": 0,
        "show_rejected": False,
    }
    for key, value in params.items():
        radius_is_inactive = key == "radius" and location_mode not in {"near", "remote_or_near"}
        if value == defaults[key] or radius_is_inactive:
            continue
        chip_params = {**params, key: defaults[key]}
        label = (
            f"Search: {value}"
            if key == "q"
            else "Newest first"
            if key == "sort"
            else labels.get(str(value), f"{key.replace('_', ' ').title()}: {value}")
        )
        chips.append({"label": label, "url": f"/discover?{urlencode(chip_params)}"})
    context.update(
        {
            "matches": matches,
            "query": q,
            "sort": sort,
            "posted": posted,
            "location_mode": location_mode,
            "zip_code": zip_code,
            "zip_error": zip_error,
            "radius": radius,
            "min_score": effective_minimum,
            "show_rejected": show_rejected,
            "chips": chips,
            "strong_minimum": profile.notifications.minimum_score,
            "wrong_reason_labels": WRONG_REASON_LABELS,
        }
    )
    return templates.TemplateResponse(request, "discover.html", context=context)


@app.get("/pipeline", response_class=HTMLResponse)
def pipeline(request: Request):
    context = _context(request, "pipeline")
    if get_settings().demo_mode:
        board = demo_pipeline(scored_jobs(context["profile"]))
        for jobs in board.values():
            for job in jobs:
                job.update(
                    {
                        "state": next(
                            state.casefold() for state, items in board.items() if job in items
                        ),
                        "priority": 0,
                        "notes": job.get("task", ""),
                        "follow_up_at": None,
                        "overdue": False,
                        "days_in_stage": 0,
                        "active": True,
                        "description_text": "",
                    }
                )
        context["pipeline"] = {"stages": board, "terminal": [], "events": []}
    else:
        repository = _repository()
        try:
            context["pipeline"] = repository.pipeline(context["profile"].profile.slug)
        finally:
            repository.close()
        for stage_jobs in context["pipeline"]["stages"].values():
            for index, job in enumerate(stage_jobs):
                stage_jobs[index] = _apply_visible_compensation(
                    {**job, "compensation_text": job.get("description_text")}
                )
        context["pipeline"]["terminal"] = [
            _apply_visible_compensation({**job, "compensation_text": job.get("description_text")})
            for job in context["pipeline"]["terminal"]
        ]
    context.update(
        {
            "changed_job": request.query_params.get("changed"),
            "changed_from": request.query_params.get("from"),
            "changed_to": request.query_params.get("to"),
            "message": request.query_params.get("message"),
        }
    )
    return templates.TemplateResponse(request, "pipeline.html", context=context)


@app.get("/fit/{job_id}", response_class=HTMLResponse)
def fit_lens(request: Request, job_id: str):
    context = _context(request, "today")
    if get_settings().demo_mode:
        matches = scored_jobs(context["profile"])
    else:
        repository = _repository()
        try:
            matches = repository.web_matches(
                context["profile"].profile.slug,
                minimum_score=0,
                limit=5000,
            )
            description_text = repository.job_description(
                context["profile"].profile.slug,
                job_id,
            )
            pipeline_data = repository.pipeline(context["profile"].profile.slug)
        finally:
            repository.close()
    job = next((item for item in matches if item["id"] == job_id), None)
    if job is None and not get_settings().demo_mode:
        pipeline_jobs = [
            item for jobs in pipeline_data["stages"].values() for item in jobs
        ] + pipeline_data["terminal"]
        job = next((item for item in pipeline_jobs if item["id"] == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    job = _apply_visible_compensation(job)
    if not get_settings().demo_mode:
        job["description_text"] = html_to_text(
            description_text or job.get("description_text", "")
        )
    if not job["evidence"]:
        job["evidence"] = [job["explanation"]]
    component_labels = {
        "role_alignment": "Role alignment",
        "skills": "Skills",
        "career_evidence": "Career evidence",
        "seniority": "Seniority",
        "geography": "Geography",
        "compensation": "Compensation",
        "company_preference": "Company preference",
        "freshness": "Freshness",
    }
    components = [
        (component_labels.get(key, key.replace("_", " ").title()), value)
        for key, value in job.get("component_scores", {}).items()
    ]
    if not components:
        components = [
            ("Evidence match", min(100, round(job["score"] + 2))),
            ("Career direction", min(100, round(job["score"]))),
            ("Constraints", 100),
            ("Confidence", max(0, round(job["score"] - 6))),
        ]
    context.update(
        {
            "job": job,
            "components": components,
            "requirements": [item.split(":", 1)[-1].strip() for item in job["evidence"]],
        }
    )
    return templates.TemplateResponse(request, "fit.html", context=context)


@app.get("/companies", response_class=HTMLResponse)
def companies(request: Request):
    context = _context(request, "companies")
    if get_settings().demo_mode:
        context["companies"] = demo_companies()
    else:
        repository = _repository()
        try:
            context["companies"] = repository.company_directory(context["profile"].profile.slug)
        finally:
            repository.close()
        if get_settings().auth_mode == "supabase":
            for company in context["companies"]:
                company["source_url"] = None
    return templates.TemplateResponse(request, "companies.html", context=context)


@app.post("/actions/{job_id}/{state}", include_in_schema=False)
def update_action(request: Request, job_id: str, state: str):
    if get_settings().demo_mode:
        return RedirectResponse("/pipeline", status_code=303)
    _same_origin(request)
    repository = _repository()
    try:
        change = repository.set_action(_profile(request).profile.slug, job_id, state)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        repository.close()
    destination = (
        "/pipeline?"
        f"changed={quote(job_id)}&from={quote(change['from_state'] or '')}"
        f"&to={quote(state)}&message={quote(f'Moved to {state.title()}')}"
    )
    return RedirectResponse(destination, status_code=303)


def _same_origin(request: Request) -> None:
    """Reject cross-origin mutations.

    Compares against the configured public origin, not request.base_url.
    Behind a TLS-terminating proxy base_url reports http:// while browsers
    always send an https:// Origin, so every mutation would 403. This
    mirrors the production origin gate in the middleware.
    """
    origin = request.headers.get("origin")
    if not origin:
        return
    settings = get_settings()
    allowed = {settings.public_base_url.rstrip("/")}
    if not settings.is_production:
        allowed.add(str(request.base_url).rstrip("/"))
    if origin.rstrip("/") not in allowed:
        raise HTTPException(status_code=403, detail="Cross-origin action rejected")


async def _form_fields(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8", errors="replace")
    return {key: values[-1] for key, values in parse_qs(body).items()}


@app.post("/pipeline")
async def update_pipeline(request: Request):
    """Handle all pipeline mutations on the browser-safe canonical page URL."""
    if get_settings().demo_mode:
        return RedirectResponse("/pipeline", status_code=303)
    _same_origin(request)
    fields = await _form_fields(request)
    job_id = fields.get("job_id", "")
    operation = fields.get("operation", "")
    if not job_id:
        raise HTTPException(status_code=400, detail="Job is required")
    if operation == "stage":
        return update_action(request, job_id, fields.get("state", ""))
    if operation == "details":
        return _update_action_details(request, job_id, fields)
    if operation == "unsave":
        return unsave_action(request, job_id)
    if operation == "undo":
        return undo_action(request, job_id)
    if operation == "dismiss":
        return dismiss_pipeline_action(request, job_id)
    raise HTTPException(status_code=400, detail="Unknown pipeline operation")


@app.post("/pipeline-actions/{job_id}/details")
async def update_action_details(request: Request, job_id: str):
    if get_settings().demo_mode:
        return RedirectResponse("/pipeline", status_code=303)
    _same_origin(request)
    fields = await _form_fields(request)
    return _update_action_details(request, job_id, fields)


def _update_action_details(
    request: Request,
    job_id: str,
    fields: dict[str, str],
):
    follow_up_at = None
    if fields.get("follow_up_at"):
        try:
            follow_up_at = datetime.fromisoformat(fields["follow_up_at"]).replace(tzinfo=UTC)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid follow-up date") from exc
    try:
        priority = int(fields.get("priority", "0"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid priority") from exc
    close_after_save = fields.get("close") == "true"
    repository = _repository()
    try:
        repository.update_action_details(
            _profile(request).profile.slug,
            job_id,
            notes=fields.get("notes", ""),
            priority=priority,
            follow_up_at=follow_up_at,
            closed_reason=fields.get("closed_reason"),
        )
        if close_after_save:
            repository.set_action(_profile(request).profile.slug, job_id, "closed")
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        repository.close()
    return RedirectResponse(f"/pipeline?message={quote('Job details updated')}", status_code=303)


@app.post("/pipeline-actions/{job_id}/unsave")
def unsave_action(request: Request, job_id: str):
    if get_settings().demo_mode:
        return RedirectResponse("/pipeline", status_code=303)
    _same_origin(request)
    repository = _repository()
    try:
        previous = repository.unsave_action(_profile(request).profile.slug, job_id)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        repository.close()
    return RedirectResponse(
        "/pipeline?"
        f"changed={quote(job_id)}&from={quote(previous)}&to="
        f"&message={quote('Removed from pipeline')}",
        status_code=303,
    )


@app.post("/pipeline-actions/{job_id}/undo")
def undo_action(request: Request, job_id: str):
    if get_settings().demo_mode:
        return RedirectResponse("/pipeline", status_code=303)
    _same_origin(request)
    repository = _repository()
    try:
        restored = repository.undo_action(_profile(request).profile.slug, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        repository.close()
    label = restored.title() if restored else "Discover"
    return RedirectResponse(
        f"/pipeline?message={quote(f'Undone — restored to {label}')}",
        status_code=303,
    )


@app.post("/feedback/{job_id}/clear")
def clear_feedback(request: Request, job_id: str):
    if get_settings().demo_mode:
        return RedirectResponse("/discover", status_code=303)
    _same_origin(request)
    repository = _repository()
    try:
        repository.clear_match_feedback(_profile(request).profile.slug, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        repository.close()
    return RedirectResponse("/discover", status_code=303)


@app.post("/discover")
async def update_discover_feedback(request: Request):
    """Handle feedback on the browser-safe canonical Discover page URL."""
    if get_settings().demo_mode:
        return RedirectResponse("/discover", status_code=303)
    _same_origin(request)
    fields = await _form_fields(request)
    job_id = fields.get("job_id", "")
    verdict = fields.get("verdict", "")
    if not job_id:
        raise HTTPException(status_code=400, detail="Job is required")
    if verdict == "clear":
        return clear_feedback(request, job_id)
    return _update_feedback(request, job_id, verdict, fields)


@app.post("/feedback/{job_id}/{verdict}")
async def update_feedback(
    request: Request,
    job_id: str,
    verdict: str,
):
    if get_settings().demo_mode:
        return RedirectResponse("/discover", status_code=303)
    _same_origin(request)
    fields = await _form_fields(request)
    return _update_feedback(request, job_id, verdict, fields)


def _update_feedback(
    request: Request,
    job_id: str,
    verdict: str,
    fields: dict[str, str],
):
    reason = fields.get("reason", "")[:500] or None
    wrong_reason_code = fields.get("wrong_reason_code") or None
    repository = _repository()
    try:
        repository.set_match_feedback(
            _profile(request).profile.slug,
            job_id,
            verdict,
            wrong_reason_code=wrong_reason_code,
            reason=reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        repository.close()
    return RedirectResponse("/discover", status_code=303)


@app.post("/pipeline-actions/{job_id}/dismiss")
def dismiss_pipeline_action(request: Request, job_id: str):
    """Dismiss a pipeline job and capture an explicit poor-fit quality signal."""
    if get_settings().demo_mode:
        return RedirectResponse("/pipeline", status_code=303)
    _same_origin(request)
    repository = _repository()
    try:
        try:
            repository.set_match_feedback(
                _profile(request).profile.slug,
                job_id,
                "wrong",
                wrong_reason_code="not_interested",
                reason="Dismissed from pipeline as poor fit",
            )
        except LookupError:
            # A closed listing can remain in the durable pipeline after its
            # current match is no longer feedback-eligible.
            pass
        repository.set_action(_profile(request).profile.slug, job_id, "dismissed")
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        repository.close()
    return RedirectResponse(
        f"/pipeline?message={quote('Dismissed and matcher feedback recorded')}",
        status_code=303,
    )


@app.get("/feedback/export.md")
def export_wrong_feedback(request: Request):
    """Download active Wrong verdicts as profile-calibration evidence."""
    profile = _profile(request)
    if get_settings().demo_mode:
        records: list[dict] = []
    else:
        repository = _repository()
        try:
            records = repository.wrong_feedback_records(profile.profile.slug)
        finally:
            repository.close()
    content = render_calibration_markdown(profile.profile.display_name, records)
    return Response(
        content=content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{profile.profile.slug}-wrong-feedback.md"'
            )
        },
    )


@app.get("/intelligence", response_class=HTMLResponse)
def intelligence(request: Request):
    context = _context(request, "intelligence")
    profile = context["profile"]
    if get_settings().demo_mode:
        overrides = {family.id: 0 for family in profile.role_families}
        matches = _apply_role_thresholds(profile, scored_jobs(profile), overrides)
        market_data = {
            "overview": {
                "observed_since": datetime.now(UTC),
                "active_jobs": len(matches),
                "scored_jobs": len(matches),
                "eligible_jobs": len(matches),
                "score_70_plus": sum(item["score"] >= 70 for item in matches),
                "score_80_plus": sum(item["score"] >= 80 for item in matches),
                "score_88_plus": sum(item["score"] >= 88 for item in matches),
                "maximum_score": max((item["score"] for item in matches), default=0),
                "remote_eligible": sum(item["workplace"] == "remote" for item in matches),
                "structured_salary_eligible": sum(
                    item["compensation"] is not None for item in matches
                ),
                "saved_jobs": 0,
                "tracked_applications": 0,
                "active_responses": 0,
                "historical_applications": 0,
                "new_jobs_24h": len(matches),
                "removed_jobs_7d": 0,
            },
            "providers": [],
            "exclusions": [],
        }
        source_health = {"latest_scan": None, "boards": []}
        quality = {
            "reviewed": 0,
            "great": 0,
            "maybe": 0,
            "wrong": 0,
            "useful_rate": None,
            "wrong_reasons": [],
        }
    else:
        repository = _repository()
        try:
            raw_matches = repository.web_matches(
                profile.profile.slug,
                minimum_score=0,
                limit=5000,
            )
            overrides = repository.role_thresholds(profile.profile.slug)
            matches = _apply_role_thresholds(profile, raw_matches, overrides)
            quality = repository.match_quality(profile.profile.slug)
            source_health = repository.source_health()
            market_data = repository.market_intelligence(profile.profile.slug)
        finally:
            repository.close()
    context["intelligence"] = _compile_intelligence(
        profile,
        matches,
        market_data,
        source_health,
        quality,
        overrides,
    )
    return templates.TemplateResponse(request, "intelligence.html", context=context)


@app.get("/ops")
def operations():
    """Private machine-readable operational state for diagnosis and smoke tests."""
    if get_settings().demo_mode:
        return {"status": "demo", "latest_scan": None, "boards": []}
    repository = _repository()
    try:
        health = repository.source_health()
    finally:
        repository.close()
    boards = health["boards"]
    degraded = sum(board["validation_status"] not in {"healthy", "pending"} for board in boards)
    return {
        "status": "degraded" if degraded else "ok",
        "degraded_boards": degraded,
        **health,
    }


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request):
    context = _context(request, "profile")
    profile = context["profile"]
    raw_matches = scored_jobs(profile) if get_settings().demo_mode else []
    overrides: dict[str, int] = {}
    if not get_settings().demo_mode:
        repository = _repository()
        try:
            raw_matches = repository.web_matches(
                profile.profile.slug,
                minimum_score=0,
                limit=5000,
            )
            overrides = repository.role_thresholds(profile.profile.slug)
        finally:
            repository.close()
    family_scores: dict[str, list[float]] = defaultdict(list)
    for item in raw_matches:
        family = matched_role_family(profile, item["title"])
        if family:
            family_scores[family.id].append(float(item["score"]))
    context["role_families"] = [
        {
            **family.model_dump(),
            "threshold": overrides.get(family.id, family.threshold),
            "default_threshold": family.threshold,
            "scores": family_scores[family.id],
            "visible_count": sum(
                score >= overrides.get(family.id, family.threshold)
                for score in family_scores[family.id]
            ),
        }
        for family in profile.role_families
    ]
    context["target_count"] = len(profile.role_families)
    return templates.TemplateResponse(request, "profile.html", context=context)


@app.post("/profile/role-threshold/{family_id}/{threshold}")
def update_role_threshold(
    request: Request,
    family_id: str,
    threshold: int,
):
    profile = _profile(request)
    try:
        profile.role_family(family_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not 0 <= threshold <= 100:
        raise HTTPException(status_code=400, detail="Threshold must be between 0 and 100")
    _same_origin(request)
    if not get_settings().demo_mode:
        repository = _repository()
        try:
            repository.set_role_threshold(profile.profile.slug, family_id, threshold)
        finally:
            repository.close()
    return RedirectResponse(f"/profile?family={family_id}", status_code=303)


@app.post("/profile/role-threshold-reset/{family_id}")
def reset_role_threshold(request: Request, family_id: str):
    profile = _profile(request)
    try:
        profile.role_family(family_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _same_origin(request)
    if not get_settings().demo_mode:
        repository = _repository()
        try:
            repository.reset_role_threshold(profile.profile.slug, family_id)
        finally:
            repository.close()
    return RedirectResponse(f"/profile?family={family_id}", status_code=303)


@app.get("/healthz")
async def healthz():
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "environment": settings.environment,
        "demo_mode": settings.demo_mode,
    }


@app.get("/readyz")
def readyz():
    """Verify that the app and its required live dependency can serve traffic."""
    settings = get_settings()
    if settings.demo_mode:
        return {"status": "ready", "database": "demo"}
    repository = _repository()
    started = time.perf_counter()
    try:
        with repository.connection() as connection:
            connection.execute("select 1").fetchone()
    except Exception:
        logger.exception(
            "dependency_unavailable",
            extra={
                "event": "dependency_check",
                "dependency": "postgres",
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return JSONResponse(
            {"status": "unavailable", "database": "unavailable"},
            status_code=503,
        )
    finally:
        repository.close()
    return {
        "status": "ready",
        "database": "ok",
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }
