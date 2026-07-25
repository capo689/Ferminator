"""Tests for location and salary parsing."""

from anthropic_tracker.parser import (
    detect_comp_type,
    normalize_currency,
    parse_compensation,
    parse_locations,
)
from tests.fixtures import (
    SAMPLE_JOB_HTML_GBP,
    SAMPLE_JOB_HTML_NO_SALARY,
    SAMPLE_JOB_HTML_REGEX_FALLBACK,
    SAMPLE_JOB_HTML_USD,
)


class TestParseLocations:
    def test_single_location(self):
        assert parse_locations("San Francisco, CA") == ["San Francisco, CA"]

    def test_semicolon_separated(self):
        result = parse_locations("New York City, NY; San Francisco, CA")
        assert result == ["New York City, NY", "San Francisco, CA"]

    def test_pipe_separated(self):
        result = parse_locations("San Francisco, CA | New York City, NY | Seattle, WA")
        assert result == ["New York City, NY", "San Francisco, CA", "Seattle, WA"]

    def test_mixed_delimiters(self):
        raw = "Atlanta, GA; Austin, TX; Boston, MA; Chicago, IL; New York City, NY | Seattle, WA; San Francisco, CA | New York City, NY; Washington, DC"
        result = parse_locations(raw)
        assert result == [
            "Atlanta, GA", "Austin, TX", "Boston, MA", "Chicago, IL",
            "New York City, NY", "San Francisco, CA", "Seattle, WA", "Washington, DC",
        ]

    def test_deduplication(self):
        result = parse_locations("San Francisco, CA; San Francisco, CA")
        assert result == ["San Francisco, CA"]

    def test_empty_string(self):
        assert parse_locations("") == []

    def test_none_like(self):
        assert parse_locations("   ") == []

    def test_sorted_output(self):
        result = parse_locations("Zurich; Amsterdam; Berlin")
        assert result == ["Amsterdam", "Berlin", "Zurich"]


class TestNormalizeCurrency:
    def test_usd(self):
        amount, currency = normalize_currency("$290,000")
        assert amount == 29000000
        assert currency == "USD"

    def test_gbp(self):
        amount, currency = normalize_currency("£195,000")
        assert amount == 19500000
        assert currency == "GBP"

    def test_eur(self):
        amount, currency = normalize_currency("€120,000")
        assert amount == 12000000
        assert currency == "EUR"

    def test_with_currency_code(self):
        amount, currency = normalize_currency("$435,000 USD")
        assert amount == 43500000
        assert currency == "USD"

    def test_european_format(self):
        amount, currency = normalize_currency("€120.000")
        assert amount == 12000000
        assert currency == "EUR"

    def test_invalid(self):
        amount, currency = normalize_currency("not a salary")
        assert amount == 0


class TestDetectCompType:
    def test_base_salary(self):
        assert detect_comp_type("Annual base salary range") == "annual"

    def test_ote(self):
        assert detect_comp_type("On-target earnings for this role") == "ote"

    def test_total_comp(self):
        assert detect_comp_type("Total target compensation") == "ote"


class TestParseCompensation:
    def test_structured_usd(self):
        result = parse_compensation(SAMPLE_JOB_HTML_USD)
        assert result is not None
        assert result["salary_min"] == 29000000
        assert result["salary_max"] == 43500000
        assert result["currency"] == "USD"

    def test_structured_gbp_ote(self):
        result = parse_compensation(SAMPLE_JOB_HTML_GBP)
        assert result is not None
        assert result["salary_min"] == 19500000
        assert result["salary_max"] == 28000000
        assert result["currency"] == "GBP"
        assert result["comp_type"] == "ote"

    def test_no_salary(self):
        result = parse_compensation(SAMPLE_JOB_HTML_NO_SALARY)
        assert result is None

    def test_regex_fallback(self):
        result = parse_compensation(SAMPLE_JOB_HTML_REGEX_FALLBACK)
        assert result is not None
        assert result["salary_min"] == 17000000
        assert result["salary_max"] == 22000000
        assert result["currency"] == "USD"

    def test_empty_html(self):
        assert parse_compensation("") is None

    def test_none(self):
        assert parse_compensation(None) is None
