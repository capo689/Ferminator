from ferminator.domain import (
    ATSProvider,
    Compensation,
    NormalizedJob,
    extract_compensation_from_text,
)


def test_extracts_annual_base_range_from_job_description() -> None:
    compensation = extract_compensation_from_text(
        "Benefits include a 401(k). The annual base salary range for this role "
        "is $175,000 – $215,000 plus equity."
    )

    assert compensation is not None
    assert compensation.minimum == 175000
    assert compensation.maximum == 215000
    assert compensation.currency == "USD"
    assert compensation.interval == "year"
    assert compensation.source == "description"


def test_extracts_k_notation_and_hourly_ranges() -> None:
    annual = extract_compensation_from_text("Base pay range: USD 150k to 190k.")
    hourly = extract_compensation_from_text("The pay range is $72–$96 per hour.")

    assert annual is not None
    assert (annual.minimum, annual.maximum) == (150000, 190000)
    assert hourly is not None
    assert (hourly.minimum, hourly.maximum, hourly.interval) == (72, 96, "hour")


def test_extracts_range_split_across_hosted_board_html() -> None:
    compensation = extract_compensation_from_text(
        '<div class="title">The annual salary range for this full-time position is</div>'
        '<div class="pay-range"><span>$66,000</span>'
        '<span class="divider">&amp;mdash;</span><span>$124,000 USD</span></div>'
    )

    assert compensation is not None
    assert compensation.minimum == 66000
    assert compensation.maximum == 124000
    assert compensation.interval == "year"


def test_does_not_mistake_benefit_numbers_for_salary() -> None:
    assert extract_compensation_from_text(
        "Benefits include a $1,500 learning stipend and a 401(k) match."
    ) is None


def test_structured_compensation_wins_over_description_fallback() -> None:
    job = NormalizedJob(
        provider=ATSProvider.GREENHOUSE,
        board_key="example",
        source_job_id="1",
        company_slug="example",
        company_name="Example",
        title="Creative Director",
        description_text="Annual base salary range: $175,000–$215,000.",
        compensation=Compensation(
            minimum=180000,
            maximum=220000,
            currency="USD",
            interval="year",
        ),
        job_url="https://example.com/job",
    )

    assert job.compensation is not None
    assert (job.compensation.minimum, job.compensation.maximum) == (180000, 220000)
    assert job.compensation.source == "structured"


def test_normalized_job_does_not_extract_before_visibility_approval() -> None:
    job = NormalizedJob(
        provider=ATSProvider.GREENHOUSE,
        board_key="example",
        source_job_id="1",
        company_slug="example",
        company_name="Example",
        title="Creative Director",
        description_text="The compensation range is $165,000 to $205,000 annually.",
        job_url="https://example.com/job",
    )

    assert job.compensation is None
