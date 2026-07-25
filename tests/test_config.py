"""Tests for config resolution: company list parsing and DB path."""

from pathlib import Path

import pytest

from anthropic_tracker.config import get_companies, get_db_path


class TestGetCompanies:
    def test_defaults_to_anthropic(self):
        assert get_companies() == ["anthropic"]

    def test_parses_comma_separated_list(self, monkeypatch):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai,notion")
        assert get_companies() == ["anthropic", "openai", "notion"]

    def test_strips_whitespace_and_lowercases(self, monkeypatch):
        monkeypatch.setenv("TRACKER_COMPANIES", " Anthropic , OpenAI ")
        assert get_companies() == ["anthropic", "openai"]

    def test_drops_empty_entries_and_dedupes(self, monkeypatch):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,,anthropic,openai")
        assert get_companies() == ["anthropic", "openai"]


class TestGetDbPath:
    def test_explicit_db_path_wins_outright(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
        explicit = str(tmp_path / "custom.db")
        assert get_db_path(explicit, "openai") == Path(explicit)

    def test_single_company_uses_plain_filename(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
        assert get_db_path() == tmp_path / "tracker.db"

    def test_multiple_companies_suffix_by_slug(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
        monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
        assert get_db_path(company="openai") == tmp_path / "tracker-openai.db"
        assert get_db_path(company="anthropic") == tmp_path / "tracker-anthropic.db"

    def test_multiple_companies_default_to_first_when_unspecified(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACKER_COMPANIES", "openai,anthropic")
        monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
        assert get_db_path() == tmp_path / "tracker-openai.db"

    def test_path_traversal_slug_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
        monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
        with pytest.raises(ValueError):
            get_db_path(company="../../etc/passwd")
        with pytest.raises(ValueError):
            get_db_path(company="a/b")

    def test_safe_slugs_with_hyphens_and_underscores_still_resolve(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
        monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
        assert get_db_path(company="openai") == tmp_path / "tracker-openai.db"
        assert get_db_path(company="my-company_1") == tmp_path / "tracker-my-company_1.db"

    def test_mixed_case_company_resolves_same_as_lowercase(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
        monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
        assert get_db_path(None, "OpenAI") == get_db_path(None, "openai")
        assert get_db_path(None, "OpenAI") == tmp_path / "tracker-openai.db"
