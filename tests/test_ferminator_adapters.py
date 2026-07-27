import httpx
import pytest

from ferminator.adapters.ashby import AshbyAdapter
from ferminator.adapters.bamboohr import BambooHRAdapter
from ferminator.adapters.base import AdapterError, BaseAdapter
from ferminator.adapters.breezy import BreezyAdapter
from ferminator.adapters.greenhouse import GreenhouseAdapter
from ferminator.adapters.lever import LeverAdapter
from ferminator.adapters.rippling import RipplingAdapter
from ferminator.adapters.smartrecruiters import SmartRecruitersAdapter
from ferminator.adapters.workable import WorkableAdapter
from ferminator.adapters.workday import WorkdayAdapter
from ferminator.domain import ATSProvider, BoardRef, WorkplaceType


def board(provider, key="example"):
    return BoardRef(
        provider=provider,
        company_slug="example-company",
        company_name="Example Company",
        board_key=key,
        source_url="https://example.com/careers",
    )


class FixtureAdapter(BaseAdapter):
    provider = ATSProvider.GREENHOUSE
    max_attempts = 1

    def fetch_jobs(self, board):
        return []


def test_adapter_rejects_successful_non_json_response():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                text="<html>maintenance</html>",
                headers={"content-type": "text/html"},
            )
        )
    )
    adapter = FixtureAdapter(client)

    with pytest.raises(AdapterError) as error:
        adapter.get_json("https://example.com/jobs")

    assert error.value.code == "unexpected_content_type"


def test_adapter_error_does_not_expose_provider_url():
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(503))
    )
    adapter = FixtureAdapter(client)

    with pytest.raises(AdapterError) as error:
        adapter.get_json("https://example.com/private-board-token")

    assert error.value.code == "provider_http_503"
    assert "private-board-token" not in str(error.value)


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


def test_bamboohr_structured_location_schema_drift():
    job = BambooHRAdapter().normalize(
        board(ATSProvider.BAMBOOHR),
        {
            "id": 43,
            "jobOpeningName": "AI Operations Lead",
            "description": "Build systems.",
            "location": {
                "city": "Saskatoon",
                "addressRegion": "SK",
                "addressCountry": "Canada",
            },
            "locationType": "On Site",
        },
    )

    assert job.locations[0].label == "Saskatoon, SK, Canada"
    assert job.locations[0].region == "SK"
    assert job.locations[0].country == "Canada"


def test_breezy_normalization():
    job = BreezyAdapter().normalize(
        board(ATSProvider.BREEZY),
        {
            "id": "breezy-1",
            "name": "AI Strategist",
            "url": "https://example.breezy.hr/p/breezy-1",
            "published_date": "2026-07-22T10:00:00Z",
            "type": {"name": "Full-Time"},
            "department": "Strategy",
            "locations": [
                {
                    "name": "Atlanta, GA",
                    "city": "Atlanta",
                    "state": {"id": "GA"},
                    "country": {"id": "US", "name": "United States"},
                    "primary": True,
                    "is_remote": True,
                }
            ],
        },
    )

    assert job.workplace_type == WorkplaceType.REMOTE
    assert job.locations[0].country_code == "US"


def test_workday_uses_distinct_external_path_as_identity():
    job = WorkdayAdapter().normalize(
        board(ATSProvider.WORKDAY, "example/External"),
        {
            "title": "AI Program Lead",
            "externalPath": "/job/Remote/AI-Program-Lead_REQ-1",
            "locationsText": "Remote, United States",
            "bulletFields": ["REQ-1"],
            "timeType": "Full time",
        },
    )

    assert job.source_job_id == "/job/Remote/AI-Program-Lead_REQ-1"
    assert job.raw_metadata["requisition_id"] == "REQ-1"
    assert job.workplace_type == WorkplaceType.REMOTE


def test_rippling_normalization():
    job = RipplingAdapter().normalize(
        board(ATSProvider.RIPPLING),
        {
            "id": "rippling-1",
            "name": "Content Operations Lead",
            "url": "https://ats.rippling.com/example/jobs/rippling-1",
            "department": {"name": "Marketing"},
            "locations": [
                {
                    "name": "Remote (United States)",
                    "country": "United States",
                    "countryCode": "US",
                    "workplaceType": "REMOTE",
                }
            ],
        },
    )

    assert job.department == "Marketing"
    assert job.workplace_type == WorkplaceType.REMOTE


def test_workday_pages_past_the_first_when_total_resets_to_zero():
    """Regression: Workday reports the real total only on page one and sends 0
    afterwards. `payload.get("total") or len(rows)` then fell back to the row
    count, so `len(rows) >= total` was trivially true and every board stopped at
    exactly 40 jobs. Eight production boards were frozen there."""
    from ferminator.adapters.workday import WorkdayAdapter
    from ferminator.domain import ATSProvider, BoardRef

    pages = [
        {"total": 50, "jobPostings": [{"externalPath": f"/j{i}", "title": f"T{i}"} for i in range(20)]},
        {"total": 0, "jobPostings": [{"externalPath": f"/j{i}", "title": f"T{i}"} for i in range(20, 40)]},
        {"total": 0, "jobPostings": [{"externalPath": f"/j{i}", "title": f"T{i}"} for i in range(40, 50)]},
    ]
    calls = []

    class Adapter(WorkdayAdapter):
        def post_json(self, url, payload):
            calls.append(payload["offset"])
            return pages[len(calls) - 1]

    board = BoardRef(
        provider=ATSProvider.WORKDAY,
        board_key="tenant/site",
        company_slug="acme",
        company_name="Acme",
        source_url="https://tenant.wd1.myworkdayjobs.com/site",
    )
    jobs = Adapter().fetch_jobs(board)

    assert len(jobs) == 50, f"stopped early at {len(jobs)}; the board reported 50"
    assert calls == [0, 20, 40]


def test_workday_skips_malformed_postings_instead_of_losing_the_board():
    """One posting missing title or externalPath used to raise KeyError and
    abort the whole fetch, so a 2,000-job board ingested nothing."""
    from ferminator.adapters.workday import WorkdayAdapter
    from ferminator.domain import ATSProvider, BoardRef

    page = {
        "total": 3,
        "jobPostings": [
            {"externalPath": "/good", "title": "Real Job"},
            {"title": "No path"},
            {"externalPath": "/no-title"},
        ],
    }

    class Adapter(WorkdayAdapter):
        def post_json(self, url, payload):
            return page

    board = BoardRef(
        provider=ATSProvider.WORKDAY,
        board_key="tenant/site",
        company_slug="acme",
        company_name="Acme",
        source_url="https://tenant.wd1.myworkdayjobs.com/site",
    )
    jobs = Adapter().fetch_jobs(board)

    assert len(jobs) == 1
    assert jobs[0].title == "Real Job"
