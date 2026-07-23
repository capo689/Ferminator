"""Ferminator web application."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ferminator import __version__
from ferminator.demo import demo_companies, demo_pipeline, scored_jobs
from ferminator.profiles import CareerProfile, load_profile
from ferminator.settings import get_settings

PACKAGE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.validate_runtime()
    load_profile(settings.profile_path)
    yield


app = FastAPI(
    title="Ferminator Career Intelligence",
    version=__version__,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")


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


@app.get("/", response_class=HTMLResponse)
async def today(request: Request):
    context = _context(request, "today")
    matches = scored_jobs(context["profile"])
    context.update(
        {
            "matches": matches,
            "lead": matches[0],
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
    matches = scored_jobs(context["profile"])
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
    context["stages"] = demo_pipeline(scored_jobs(context["profile"]))
    return templates.TemplateResponse(request, "pipeline.html", context=context)


@app.get("/companies", response_class=HTMLResponse)
async def companies(request: Request):
    context = _context(request, "companies")
    context["companies"] = demo_companies()
    return templates.TemplateResponse(request, "companies.html", context=context)


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

