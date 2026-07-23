from ferminator.adapters.ashby import AshbyAdapter
from ferminator.adapters.bamboohr import BambooHRAdapter
from ferminator.adapters.greenhouse import GreenhouseAdapter
from ferminator.adapters.lever import LeverAdapter
from ferminator.adapters.smartrecruiters import SmartRecruitersAdapter
from ferminator.adapters.workable import WorkableAdapter
from ferminator.domain import ATSProvider, BoardRef, WorkplaceType


def board(provider, key="example"):
    return BoardRef(
        provider=provider,
        company_slug="example-company",
        company_name="Example Company",
        board_key=key,
        source_url="https://example.com/careers",
    )


def test_greenhouse_normalization():
    job = GreenhouseAdapter().normalize(
        board(ATSProvider.GREENHOUSE),
        {
            "id": 12,
            "title": "AI Enablement Lead",
            "content": "<p>Build useful systems.</p>",
            "absolute_url": "https://example.com/12",
            "company_name": "Example Company",
            "location": {"name": "Remote - US"},
            "departments": [{"name": "Operations"}],
            "first_published": "2026-07-22T10:00:00Z",
        },
    )

    assert job.source_key == "greenhouse:example:12"
    assert job.description_text == "Build useful systems."
    assert job.workplace_type == WorkplaceType.REMOTE


def test_lever_normalization():
    job = LeverAdapter().normalize(
        board(ATSProvider.LEVER),
        {
            "id": "abc",
            "text": "AI Operations Manager",
            "descriptionPlain": "Build AI workflows.",
            "categories": {
                "location": "Remote",
                "allLocations": ["Remote"],
                "department": "Operations",
                "commitment": "Full-time",
            },
            "workplaceType": "remote",
            "hostedUrl": "https://jobs.lever.co/example/abc",
            "applyUrl": "https://jobs.lever.co/example/abc/apply",
            "salaryRange": {
                "min": 150000,
                "max": 190000,
                "currency": "USD",
                "interval": "year",
            },
        },
    )

    assert job.compensation.minimum == 150000
    assert job.workplace_type == WorkplaceType.REMOTE


def test_ashby_normalization():
    job = AshbyAdapter().normalize(
        board(ATSProvider.ASHBY),
        {
            "id": "ash-1",
            "title": "Director of Enablement",
            "location": "United States",
            "isRemote": True,
            "workplaceType": "Remote",
            "descriptionPlain": "Enable teams.",
            "department": "People",
            "jobUrl": "https://jobs.ashbyhq.com/example/ash-1",
            "applyUrl": "https://jobs.ashbyhq.com/example/ash-1/application",
            "publishedAt": "2026-07-22T10:00:00Z",
        },
    )

    assert job.workplace_type == WorkplaceType.REMOTE
    assert job.department == "People"


def test_smartrecruiters_normalization():
    job = SmartRecruitersAdapter().normalize(
        board(ATSProvider.SMARTRECRUITERS, "Example"),
        {
            "id": "smart-1",
            "name": "Knowledge Operations Lead",
            "company": {"name": "Example Company"},
            "location": {"city": "Los Angeles", "region": "CA", "country": "US"},
            "department": {"label": "Operations"},
            "typeOfEmployment": {"label": "Full-time"},
            "jobAd": {"sections": {"jobDescription": {"text": "<p>Build systems.</p>"}}},
            "postingUrl": "https://jobs.smartrecruiters.com/Example/smart-1",
            "releasedDate": "2026-07-22T10:00:00Z",
        },
    )

    assert job.description_text == "Build systems."
    assert job.locations[0].city == "Los Angeles"


def test_workable_normalization():
    job = WorkableAdapter().normalize(
        board(ATSProvider.WORKABLE),
        {
            "shortcode": "WORK1",
            "title": "AI Program Manager",
            "description": "<p>Lead adoption.</p>",
            "department": "Operations",
            "employment_type": "Full-time",
            "telecommuting": True,
            "locations": [{"city": "Remote", "country": "United States"}],
            "shortlink": "https://apply.workable.com/j/WORK1",
            "url": "https://example.workable.com/jobs/1",
            "application_url": "https://example.workable.com/jobs/1/candidates/new",
        },
    )

    assert job.workplace_type == WorkplaceType.REMOTE
    assert job.description_text == "Lead adoption."


def test_bamboohr_normalization():
    job = BambooHRAdapter().normalize(
        board(ATSProvider.BAMBOOHR),
        {
            "id": 42,
            "jobOpeningName": "Technical Content Lead",
            "description": "<p>Teach customers.</p>",
            "departmentLabel": "Marketing",
            "employmentStatusLabel": "Full Time",
            "locationType": 1,
            "isRemote": True,
            "datePosted": "2026-07-22",
        },
    )

    assert job.source_job_id == "42"
    assert job.workplace_type == WorkplaceType.REMOTE
    assert job.description_text == "Teach customers."

