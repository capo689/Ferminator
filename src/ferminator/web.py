"""Ferminator web application."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ferminator import __version__
from ferminator.demo import demo_companies, demo_pipeline, scored_jobs
from ferminator.observability import configure_logging
from ferminator.profiles import CareerProfile, load_profile
from ferminator.repository import PostgresRepository
from ferminator.settings import get_settings

PACKAGE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
logger = logging.getLogger("ferminator.web")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.validate_runtime()
    load_profile(settings.profile_path)
    yield


app = FastAPI(
    title="Ferminator Career Intelligence",
    version=__version__,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path},
        )
        raise
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    logger.info(
        "request_complete",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return response


@app.middleware("http")
async def alpha_access_gate(request: Request, call_next):
    settings = get_settings()
    if (
        settings.auth_mode != "shared_password"
        or request.url.path == "/healthz"
        or request.url.path.startswith("/static/")
    ):
        return await call_next(request)
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Basic "):
        import base64
        import binascii

        try:
            decoded = base64.b64decode(authorization[6:], validate=True).decode()
            _, password = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError, binascii.Error):
            password = ""
        if settings.valid_alpha_password(password):
            return await call_next(request)
    return Response(
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Ferminator private alpha"'},
    )


def _profile() -> CareerProfile:
    return load_profile(get_settings().profile_path)


def _context(request: Request, active: str) -> dict:
    profile = _profile()
    return {
        "request": request,
        "active": active,
        "profile": profile,
        "display_name": profile.profile.display_name,
        "demo_mode": get_settings().demo_mode,
        "version": __version__,
    }


def _repository() -> PostgresRepository:
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for live dashboard data")
    return PostgresRepository(database_url, min_size=1, max_size=2)


def _matches(profile: CareerProfile, *, minimum_score: float = 0) -> list[dict]:
    if get_settings().demo_mode:
        return scored_jobs(profile)
    repository = _repository()
    try:
        return repository.web_matches(profile.profile.slug, minimum_score=minimum_score)
    finally:
        repository.close()


@app.get("/", response_class=HTMLResponse)
async def today(request: Request):
    context = _context(request, "today")
    matches = _matches(
        context["profile"],
        minimum_score=context["profile"].notifications.minimum_score,
    )
    context.update(
        {
            "matches": matches,
            "lead": matches[0] if matches else None,
            "secondary": matches[1:3],
            "stats": {
                "new_matches": len(matches),
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
async def discover(
    request: Request,
    q: str = Query(default=""),
    remote: bool = Query(default=False),
    min_score: int = Query(default=0, ge=0, le=100),
):
    context = _context(request, "discover")
    matches = _matches(context["profile"])
    if q:
        needle = q.casefold()
        matches = [
            item for item in matches
            if needle in f"{item['title']} {item['company']} {item['department']}".casefold()
        ]
    if remote:
        matches = [item for item in matches if item["workplace"] == "remote"]
    matches = [item for item in matches if item["score"] >= min_score]
    context.update(
        {
            "matches": matches,
            "query": q,
            "remote": remote,
            "min_score": min_score,
        }
    )
    return templates.TemplateResponse(request, "discover.html", context=context)


@app.get("/pipeline", response_class=HTMLResponse)
async def pipeline(request: Request):
    context = _context(request, "pipeline")
    if get_settings().demo_mode:
        context["stages"] = demo_pipeline(scored_jobs(context["profile"]))
    else:
        repository = _repository()
        try:
            context["stages"] = repository.pipeline(context["profile"].profile.slug)
        finally:
            repository.close()
    return templates.TemplateResponse(request, "pipeline.html", context=context)


@app.get("/fit/{job_id}", response_class=HTMLResponse)
async def fit_lens(request: Request, job_id: str):
    context = _context(request, "today")
    matches = _matches(context["profile"])
    job = next((item for item in matches if item["id"] == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
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
            "requirements": [
                item.split(":", 1)[-1].strip() for item in job["evidence"]
            ],
        }
    )
    return templates.TemplateResponse(request, "fit.html", context=context)


@app.get("/companies", response_class=HTMLResponse)
async def companies(request: Request):
    context = _context(request, "companies")
    if get_settings().demo_mode:
        context["companies"] = demo_companies()
    else:
        repository = _repository()
        try:
            context["companies"] = repository.company_stats(context["profile"].profile.slug)
        finally:
            repository.close()
    return templates.TemplateResponse(request, "companies.html", context=context)


@app.post("/actions/{job_id}/{state}")
async def update_action(request: Request, job_id: str, state: str):
    if get_settings().demo_mode:
        return RedirectResponse("/pipeline", status_code=303)
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(status_code=403, detail="Cross-origin action rejected")
    repository = _repository()
    try:
        repository.set_action(_profile().profile.slug, job_id, state)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        repository.close()
    destination = "/pipeline" if state != "dismissed" else "/"
    return RedirectResponse(destination, status_code=303)


@app.get("/intelligence", response_class=HTMLResponse)
async def intelligence(request: Request):
    context = _context(request, "intelligence")
    context.update(
        {
            "market": [
                {"label": "AI enablement roles", "value": "+18%", "direction": "up"},
                {"label": "Remote leadership roles", "value": "−7%", "direction": "down"},
                {"label": "Median relevant salary", "value": "$192K", "direction": "flat"},
                {"label": "Active watched companies", "value": "11", "direction": "up"},
            ],
            "skills": [
                ("AI adoption", 88),
                ("Cross-functional leadership", 76),
                ("Enablement", 71),
                ("Knowledge systems", 58),
                ("Technical writing", 49),
            ],
        }
    )
    return templates.TemplateResponse(request, "intelligence.html", context=context)


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    context = _context(request, "profile")
    context["target_count"] = (
        len(context["profile"].high_titles) + len(context["profile"].adjacent_titles)
    )
    return templates.TemplateResponse(request, "profile.html", context=context)


@app.get("/healthz")
async def healthz():
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "environment": settings.environment,
        "demo_mode": settings.demo_mode,
    }
