"""The API contract, checked against the Pydantic side.

`evals/goldens/activity_contract_v1.json` is read by this file and by
`web/tests/contract.test.ts`. Adding a field to the Python model without updating the
fixture fails here; updating the fixture without updating the Zod schema fails there. The
two tests together are what stops the contract drifting.
"""

import json
from pathlib import Path

from surf.models import (
    Activity,
    ActivitySummary,
    LabelPass,
    SessionCandidates,
    SessionTrack,
    StoredLabel,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDENS = REPO_ROOT / "evals" / "goldens"
CONTRACT = json.loads((GOLDENS / "activity_contract_v1.json").read_text(encoding="utf-8"))
LABELING = json.loads((GOLDENS / "labeling_contract_v1.json").read_text(encoding="utf-8"))


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


# ------------------------------------------------------- the Phase 4 labeling contract

TRACK = SessionTrack.model_validate(LABELING["track"])
CANDIDATES = SessionCandidates.model_validate(LABELING["candidates"])
LABELS = [StoredLabel.model_validate(row) for row in LABELING["labels"]]
PASSES = [LabelPass.model_validate(row) for row in LABELING["passes"]]


def test_the_labeling_fixture_serialises_back_to_exactly_itself():
    """Byte-for-byte, the same guarantee the activity contract has."""
    assert TRACK.model_dump(mode="json") == LABELING["track"]
    assert CANDIDATES.model_dump(mode="json") == LABELING["candidates"]
    assert [row.model_dump(mode="json") for row in LABELS] == LABELING["labels"]
    assert [row.model_dump(mode="json") for row in PASSES] == LABELING["passes"]


def test_track_field_sets_match_the_models():
    assert set(LABELING["track"]) == set(TRACK.model_dump())
    for row in LABELING["track"]["smoothed"]:
        assert set(row) == set(TRACK.smoothed[0].model_dump())
    for row in LABELING["track"]["framed"]:
        assert set(row) == set(TRACK.framed[0].model_dump())


def test_candidate_field_sets_match_the_models():
    assert set(LABELING["candidates"]) == set(CANDIDATES.model_dump())
    for row in LABELING["candidates"]["candidates"]:
        assert set(row) == set(CANDIDATES.candidates[0].model_dump())


def test_label_and_pass_field_sets_match_the_models():
    for row in LABELING["labels"]:
        assert set(row) == set(LABELS[0].model_dump())
    for row in LABELING["passes"]:
        assert set(row) == set(PASSES[0].model_dump())


def test_the_track_fixture_still_shows_both_sides_of_the_measured_estimated_line():
    """Trimmed to only-observed rows it would prove nothing about the one rule that matters."""
    observed = {row["observed"] for row in LABELING["track"]["smoothed"]}
    assert observed == {True, False}
    assert {row["observed"] for row in LABELING["track"]["framed"]} == {True, False}

    seen = next(r for r in TRACK.smoothed if r.observed)
    blind = next(r for r in TRACK.smoothed if not r.observed)
    assert blind.position_sigma_m > seen.position_sigma_m
    assert blind.confidence < seen.confidence


def test_the_candidate_fixture_covers_a_proposal_a_human_should_distrust():
    coverage = {row["position_coverage"] for row in LABELING["candidates"]["candidates"]}
    assert 0.0 in coverage and 1.0 in coverage


def test_the_label_fixture_covers_every_state_the_ui_can_produce():
    assert {row["source"] for row in LABELING["labels"]} == {"human", "human_assisted"}
    assert {row["is_wave"] for row in LABELING["labels"]} == {True, False}
    assert any(row["supersedes"] is not None for row in LABELING["labels"])
    assert any(row["supersedes"] is None for row in LABELING["labels"])


def test_only_the_unassisted_human_labels_count_as_truth():
    """The fixture pins the rule, not just the field (ADR-0012)."""
    by_source = {row.source.value: row.counts_as_truth for row in LABELS}
    assert by_source == {"human": True, "human_assisted": False}


def test_the_pass_fixture_covers_both_sweeps():
    assert {row["kind"] for row in LABELING["passes"]} == {"blind", "assisted"}
