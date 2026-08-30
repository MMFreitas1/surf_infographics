"""The API contract, checked against the Pydantic side.

`evals/goldens/activity_contract_v1.json` is read by this file and by
`web/tests/contract.test.ts`. Adding a field to the Python model without updating the
fixture fails here; updating the fixture without updating the Zod schema fails there. The
two tests together are what stops the contract drifting.
"""

import json
from pathlib import Path

from surf.models import Activity, ActivitySummary

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads(
    (REPO_ROOT / "evals" / "goldens" / "activity_contract_v1.json").read_text(encoding="utf-8")
)


ACTIVITY = Activity.model_validate(CONTRACT["activity"])
SUMMARY = ActivitySummary.model_validate(CONTRACT["summary"])


def test_the_fixture_is_a_valid_activity():
    assert Activity.model_validate(CONTRACT["activity"]).activity_id == "contract-v1"


def test_the_activity_serialises_back_to_exactly_the_fixture():
    """Byte-for-byte: a changed field name, type or default breaks this."""
    activity = Activity.model_validate(CONTRACT["activity"])
    assert activity.model_dump(mode="json") == CONTRACT["activity"]


def test_the_fixture_is_a_valid_summary():
    summary = ActivitySummary.model_validate(CONTRACT["summary"])
    assert summary.model_dump(mode="json") == CONTRACT["summary"]


def test_activity_field_set_matches_what_the_api_emits():
    """Compared against the serialised dump, so computed fields are included as the UI sees them."""
    assert set(CONTRACT["activity"]) == set(ACTIVITY.model_dump())


def test_sample_field_set_matches_the_model():
    expected = set(ACTIVITY.samples[0].model_dump())
    for sample in CONTRACT["activity"]["samples"]:
        assert set(sample) == expected


def test_blind_window_field_set_matches_the_model():
    expected = set(ACTIVITY.blind_windows[0].model_dump())
    for window in CONTRACT["activity"]["blind_windows"]:
        assert set(window) == expected


def test_summary_field_set_matches_the_model():
    assert set(CONTRACT["summary"]) == set(SUMMARY.model_dump())


def test_the_fixture_still_covers_both_states_of_every_optional_field():
    """Guards the fixture itself: trimmed to only-present values it would test nothing."""
    samples = CONTRACT["activity"]["samples"]
    for field in ("lat", "lon", "speed_ms", "hr_bpm", "temp_c", "distance_m"):
        assert any(s[field] is not None for s in samples), f"{field} never present"
        assert any(s[field] is None for s in samples), f"{field} never absent"
    assert {s["has_position"] for s in samples} == {True, False}


def test_the_fixture_covers_both_blind_causes():
    causes = {w["cause"] for w in CONTRACT["activity"]["blind_windows"]}
    assert causes == {"no_fix", "missing_record"}
