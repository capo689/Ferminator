"""Realistic, clearly labeled demo data for local product development."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ferminator.domain import (
    ATSProvider,
    Compensation,
    JobLocation,
    NormalizedJob,
    WorkplaceType,
)
from ferminator.matching import MatchResult, score_job
from ferminator.profiles import CareerProfile


def _job(
    *,
    job_id: str,
    company: str,
    title: str,
    description: str,
    salary: tuple[int, int] | None,
    age_hours: int,
    provider: ATSProvider,
    department: str,
    workplace: WorkplaceType = WorkplaceType.REMOTE,
    location: str = "Remote — United States",
) -> NormalizedJob:
    slug = company.casefold().replace(" ", "-").replace(".", "")
    compensation = (
        Compensation(
            minimum=salary[0],
            maximum=salary[1],
            currency="USD",
            interval="year",
        )
        if salary
        else None
    )
    return NormalizedJob(
        provider=provider,
        board_key=slug,
        source_job_id=job_id,
        company_slug=slug,
        company_name=company,
        title=title,
        description_text=description,
        department=department,
        employment_type="Full-time",
        workplace_type=workplace,
        locations=[
            JobLocation(
                label=location,
                is_primary=True,
                is_remote=workplace == WorkplaceType.REMOTE,
            )
        ],
        compensation=compensation,
        job_url=f"https://example.com/{slug}/jobs/{job_id}",
        apply_url=f"https://example.com/{slug}/jobs/{job_id}/apply",
        published_at=datetime.now(UTC) - timedelta(hours=age_hours),
    )


def demo_jobs() -> list[NormalizedJob]:
    return [
        _job(
            job_id="airtable-ai-enablement",
            company="Airtable",
            title="Director, AI Enablement",
            description=(
                "Lead enterprise AI adoption and enablement programs across product and GTM. "
                "Build knowledge systems, executive communication, technical writing, and "
                "cross-functional operations that help teams use AI responsibly."
            ),
            salary=(185000, 240000),
            age_hours=6,
            provider=ATSProvider.GREENHOUSE,
            department="People & Operations",
        ),
        _job(
            job_id="notion-knowledge-ops",
            company="Notion",
            title="Senior Manager, Knowledge Operations",
            description=(
                "Design knowledge systems and content operations for an AI-first company. "
                "Partner cross-functionally on workflow design, enablement, and adoption."
            ),
            salary=(175000, 225000),
            age_hours=11,
            provider=ATSProvider.ASHBY,
            department="Operations",
        ),
        _job(
            job_id="figma-ai-programs",
            company="Figma",
            title="AI Programs Lead",
            description=(
                "Build AI adoption programs, executive communication, learning systems, and "
                "repeatable workflows across a global product organization."
            ),
            salary=(170000, 215000),
            age_hours=18,
            provider=ATSProvider.LEVER,
            department="Strategy",
        ),
        _job(
            job_id="linear-developer-education",
            company="Linear",
            title="Developer Education Lead",
            description=(
                "Create technical content, education programs, and product learning systems. "
                "Work with engineering and marketing to help teams adopt complex tools."
            ),
            salary=None,
            age_hours=30,
            provider=ATSProvider.ASHBY,
            department="Marketing",
        ),
        _job(
            job_id="asana-content-ops",
            company="Asana",
            title="Content Operations Director",
            description=(
                "Lead content operations, knowledge management, workflow design, and "
                "cross-functional planning for enterprise audiences."
            ),
            salary=(180000, 220000),
            age_hours=52,
            provider=ATSProvider.GREENHOUSE,
            department="Marketing",
            workplace=WorkplaceType.HYBRID,
            location="San Francisco, CA",
        ),
        _job(
            job_id="example-sales",
            company="Example Corp",
            title="Enterprise Account Executive",
            description="Quota-carrying sales role for enterprise software.",
            salary=(110000, 180000),
            age_hours=3,
            provider=ATSProvider.SMARTRECRUITERS,
            department="Sales",
        ),
    ]


def scored_jobs(profile: CareerProfile) -> list[dict[str, Any]]:
    results = []
    for job in demo_jobs():
        match = score_job(profile, job)
        if match.eligible:
            results.append(_job_view(job, match))
    return sorted(results, key=lambda item: item["score"], reverse=True)


def _job_view(job: NormalizedJob, match: MatchResult) -> dict[str, Any]:
    compensation = None
    if job.compensation and job.compensation.minimum is not None:
        compensation = (
            f"${job.compensation.minimum / 1000:,.0f}K–"
            f"${job.compensation.maximum / 1000:,.0f}K"
        )
    published = job.published_at or job.retrieved_at
    age_hours = max(0, int((datetime.now(UTC) - published).total_seconds() / 3600))
    freshness = f"{age_hours}h ago" if age_hours < 48 else f"{age_hours // 24}d ago"
    return {
        "id": job.source_job_id,
        "title": job.title,
        "company": job.company_name,
        "company_slug": job.company_slug,
        "company_initial": job.company_name[0],
        "department": job.department,
        "location": job.locations[0].label if job.locations else "Location unspecified",
        "workplace": job.workplace_type.value,
        "compensation": compensation,
        "score": match.score,
        "evidence": match.matched_evidence[:4],
        "concerns": match.concerns[:2],
        "explanation": match.explanation,
        "description_text": job.description_text,
        "compensation_source": "ATS" if job.compensation else None,
        "freshness": freshness,
        "provider": job.provider.value,
        "job_url": str(job.job_url),
        "apply_url": str(job.apply_url or job.job_url),
    }


def demo_pipeline(matches: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    stages = {
        "Considering": matches[1:2],
        "Preparing": matches[0:1],
        "Applied": matches[3:4],
        "Interviewing": [],
        "Offer": [],
    }
    if stages["Preparing"]:
        stages["Preparing"][0] = {
            **stages["Preparing"][0],
            "task": "Tailor leadership evidence",
            "due": "Today",
        }
    if stages["Applied"]:
        stages["Applied"][0] = {
            **stages["Applied"][0],
            "task": "Follow up with recruiter",
            "due": "Friday",
        }
    return stages


def demo_companies() -> list[dict[str, Any]]:
    return [
        {
            "name": "Airtable", "initial": "A", "provider": "greenhouse",
            "board_key": "airtable", "validation_status": "healthy", "healthy": True,
            "active_jobs": 38, "relevant_jobs": 8, "new_jobs": 3,
            "source_url": "https://job-boards.greenhouse.io/airtable",
            "last_validated_at": None,
        },
        {
            "name": "Notion", "initial": "N", "provider": "ashby",
            "board_key": "notion", "validation_status": "healthy", "healthy": True,
            "active_jobs": 42, "relevant_jobs": 6, "new_jobs": 2,
            "source_url": "https://jobs.ashbyhq.com/notion", "last_validated_at": None,
        },
        {
            "name": "Figma", "initial": "F", "provider": "greenhouse",
            "board_key": "figma", "validation_status": "healthy", "healthy": True,
            "active_jobs": 174, "relevant_jobs": 5, "new_jobs": 1,
            "source_url": "https://job-boards.greenhouse.io/figma",
            "last_validated_at": None,
        },
    ]
