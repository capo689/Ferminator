"""Shared test data constants."""

SAMPLE_JOBS = [
    {
        "id": 1001,
        "internal_job_id": 2001,
        "title": "Senior Software Engineer, Infrastructure",
        "absolute_url": "https://boards.greenhouse.io/anthropic/jobs/1001",
        "requisition_id": "REQ-1001",
        "first_published": "2026-04-01T00:00:00Z",
        "updated_at": "2026-04-10T12:00:00Z",
        "location": {"name": "San Francisco, CA"},
        "departments": [
            {"id": 100, "name": "Software Engineering (Infrastructure)",
             "child_ids": [], "parent_id": None},
        ],
        "offices": [
            {"id": 10, "name": "San Francisco",
             "location": {"name": "San Francisco, CA"},
             "child_ids": [], "parent_id": None},
        ],
        "metadata": [],
    },
    {
        "id": 1002,
        "internal_job_id": 2002,
        "title": "Account Executive, Higher Education",
        "absolute_url": "https://boards.greenhouse.io/anthropic/jobs/1002",
        "requisition_id": "REQ-1002",
        "first_published": "2026-04-05T00:00:00Z",
        "updated_at": "2026-04-12T08:00:00Z",
        "location": {"name": "New York City, NY; San Francisco, CA"},
        "departments": [
            {"id": 200, "name": "Sales",
             "child_ids": [], "parent_id": None},
        ],
        "offices": [
            {"id": 11, "name": "New York City",
             "location": {"name": "New York City, NY"},
             "child_ids": [], "parent_id": None},
            {"id": 10, "name": "San Francisco",
             "location": {"name": "San Francisco, CA"},
             "child_ids": [], "parent_id": None},
        ],
        "metadata": [],
    },
    {
        "id": 1003,
        "internal_job_id": 2003,
        "title": "Research Scientist, Interpretability",
        "absolute_url": "https://boards.greenhouse.io/anthropic/jobs/1003",
        "requisition_id": "REQ-1003",
        "first_published": "2026-03-15T00:00:00Z",
        "updated_at": "2026-04-08T16:00:00Z",
        "location": {"name": "San Francisco, CA | Seattle, WA"},
        "departments": [
            {"id": 300, "name": "AI Research & Engineering",
             "child_ids": [], "parent_id": None},
        ],
        "offices": [],
        "metadata": [],
    },
    {
        "id": 1004,
        "internal_job_id": 2004,
        "title": "Forward Deployed Engineer",
        "absolute_url": "https://boards.greenhouse.io/anthropic/jobs/1004",
        "requisition_id": "REQ-1004",
        "first_published": "2026-04-10T00:00:00Z",
        "updated_at": "2026-04-14T10:00:00Z",
        "location": {
            "name": (
                "Atlanta, GA; Austin, TX; Boston, MA; Chicago, IL; "
                "New York City, NY | Seattle, WA; San Francisco, CA | "
                "New York City, NY; Washington, DC"
            )
        },
        "departments": [
            {"id": 100, "name": "Software Engineering (Infrastructure)",
             "child_ids": [], "parent_id": None},
        ],
        "offices": [],
        "metadata": [],
    },
    {
        "id": 1005,
        "internal_job_id": 2005,
        "title": "Solutions Architect, EMEA",
        "absolute_url": "https://boards.greenhouse.io/anthropic/jobs/1005",
        "requisition_id": "REQ-1005",
        "first_published": "2026-04-12T00:00:00Z",
        "updated_at": "2026-04-14T14:00:00Z",
        "location": {"name": "London, UK"},
        "departments": [
            {"id": 200, "name": "Sales",
             "child_ids": [], "parent_id": None},
        ],
        "offices": [
            {"id": 20, "name": "London",
             "location": {"name": "London, UK"},
             "child_ids": [], "parent_id": None},
        ],
        "metadata": [],
    },
]

SAMPLE_JOB_HTML_USD = """
<div>
<h3>About the role</h3>
<p>We are looking for a Senior Software Engineer...</p>
<div class="content-pay-transparency">
  <p>Annual Salary</p>
  <div class="pay-range">
    <span>$290,000</span>
    <span class="divider">\u2014</span>
    <span>$435,000 USD</span>
  </div>
  <p>The expected total compensation includes base salary.</p>
</div>
</div>
"""

SAMPLE_JOB_HTML_GBP = """
<div>
<div class="content-pay-transparency">
  <p>On-Target Earnings</p>
  <div class="pay-range">
    <span>\u00a3195,000</span>
    <span class="divider">\u2014</span>
    <span>\u00a3280,000 GBP</span>
  </div>
</div>
</div>
"""

SAMPLE_JOB_HTML_NO_SALARY = """
<div>
<h3>About the role</h3>
<p>We are looking for a Policy Analyst...</p>
<p>No salary information provided for this role.</p>
</div>
"""

SAMPLE_JOB_HTML_REGEX_FALLBACK = """
<div>
<p>The expected salary range is $170,000-$220,000 USD annually.</p>
</div>
"""
