from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ferminator.domain import ATSProvider
from ferminator.registry import CompanyRegistry, load_registry


def test_curated_registry_only_enables_real_boards() -> None:
    registry = load_registry(Path("config/companies.yaml"))

    assert len(registry.enabled_boards) == 113
    assert {board.provider for board in registry.enabled_boards} == {
        ATSProvider.GREENHOUSE,
        ATSProvider.ASHBY,
        ATSProvider.SMARTRECRUITERS,
        ATSProvider.WORKABLE,
        ATSProvider.BAMBOOHR,
        ATSProvider.LEVER,
    }


def test_registry_rejects_duplicate_board_identity() -> None:
    payload = {
        "schema_version": 1,
        "companies": [
            {
                "slug": "one",
                "name": "One",
                "boards": [
                    {
                        "provider": "greenhouse",
                        "board_key": "same",
                        "source_url": "https://example.com/one",
                    }
                ],
            },
            {
                "slug": "two",
                "name": "Two",
                "boards": [
                    {
                        "provider": "greenhouse",
                        "board_key": "same",
                        "source_url": "https://example.com/two",
                    }
                ],
            },
        ],
    }

    with pytest.raises(ValidationError, match="combinations must be unique"):
        CompanyRegistry.model_validate(payload)
