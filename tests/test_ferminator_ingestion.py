from __future__ import annotations

import pytest

from ferminator.ingestion import IngestionPolicy, UnsafeRemovalError, plan_lifecycle


def test_lifecycle_classifies_add_remove_and_reactivate() -> None:
    plan = plan_lifecycle(
        active_ids={"active", "remove"},
        known_ids={"active", "remove", "returning"},
        incoming_ids={"active", "returning", "new"},
        policy=IngestionPolicy(max_removal_fraction=0.5),
    )

    assert plan.added == {"new"}
    assert plan.removed == {"remove"}
    assert plan.reactivated == {"returning"}
    assert plan.present == {"active", "returning", "new"}


def test_lifecycle_rejects_empty_response_for_active_board() -> None:
    with pytest.raises(UnsafeRemovalError, match="Empty response"):
        plan_lifecycle(
            active_ids={"one"},
            known_ids={"one"},
            incoming_ids=set(),
        )


def test_lifecycle_rejects_suspicious_mass_removal() -> None:
    with pytest.raises(UnsafeRemovalError, match="Removal fraction"):
        plan_lifecycle(
            active_ids={"one", "two", "three"},
            known_ids={"one", "two", "three"},
            incoming_ids={"one"},
        )
