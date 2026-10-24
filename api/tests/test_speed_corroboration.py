"""The speed-corroboration cut, against the only labels this project has (ADR-0023).

Miguel labelled the reference session's eleven settled waves on 2026-10-24 -- the first
ground truth here, and the first threshold in the pipeline set against labels rather than
against the synthetic. Three of the eleven were not waves. Two of those three are the same
artefact: a blind stretch ends, the watch back-fills its odometer in one step, and the
smoother bridges the position gap with a curve shaped exactly like a ride. Every channel
downstream then reads like a ride, and only the device's own speedometer disagrees.

**Eleven labels from one session justify a rule, not a hit rate** (ADR-0013). Nothing here
claims an accuracy figure; what it pins is that the rule still reproduces the eleven calls it
was designed against, and that the cutoff still sits inside the plateau that made it safe.

These tests need ``sample_data/`` and skip without it, which is every CI run: the file is a
GPS trace of a real session and is gitignored (CLAUDE.md). A local check, never a gate.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from surf.config import Settings
from surf.ingest import parse_file
from surf.models import WaveCandidate
from surf.pipeline.clean import CleanStage
from surf.pipeline.l1 import KinematicsStage
from surf.pipeline.l2 import FrameStage
from surf.pipeline.l3 import CandidateSet, CandidateStage
from surf.pipeline.l4 import FeatureInput, FeatureStage
from surf.pipeline.l5 import ClassifyStage

CUTOFF = 0.65
"""What ships. Inside the 0.4-0.7 plateau, and Miguel's choice of where in it."""

PLATEAU = (0.4, 0.5, 0.65, 0.7)
"""Every cutoff measured to give the same eleven answers."""

LABELLED_SPANS = (
    # Offsets from the first sample, so no date and no coordinate appears here.
    # (start_s, end_s, Miguel's call, the ratio as measured 2026-10-24)
    (570, 594, True, 0.95),
    (671, 674, True, None),  # the watch saw none of it; "already standing"
    (714, 742, True, 0.79),  # the weakest real one, and the bottom of the cut
    (941, 960, True, 0.86),
    (1271, 1288, True, 0.85),
    (1566, 1582, True, 0.94),
    (2100, 2121, False, 0.00),  # "didn't happen" -- watch recorded 0.00 against 9.50
    (2146, 2163, False, 0.38),  # "waiting for the mellow wave to form a wall, but it didnt"
    (2832, 2878, True, 0.97),
    (3191, 3224, False, 0.15),  # "didn't happen" -- 2 observed seconds of 33, 167 m apart
    (3270, 3294, True, 0.93),
)

EXPECTED_WAVES = sum(1 for *_, is_wave, _ in LABELLED_SPANS if is_wave)
"""Eight, counted from the labels rather than written down twice."""


@pytest.fixture
def measured(sample_fit: Path):
    """L4 over the eleven labelled spans of the real recording.

    The spans are pinned rather than re-proposed, because L3's proposals depend on the shore
    axis and Phase 6 is about to move it (ADR-0022). The corroboration features do not:
    ``FramedSample.speed_ms`` is a ground speed and a rotation preserves it, so these ratios
    are the same under any frame. That is what lets this fixture outlive the axis change.
    """
    cleaned = CleanStage().run(parse_file(sample_fit))
    track = KinematicsStage().run(cleaned.activity)
    framed = FrameStage().run(track)
    t0 = cleaned.activity.samples[0].t
    return FeatureStage().run(
        FeatureInput(
            candidates=CandidateSet(
                frame=framed.frame,
                candidates=[
                    WaveCandidate(t_start=t0 + start, t_end=t0 + end)
                    for start, end, _, _ in LABELLED_SPANS
                ],
            ),
            framed=framed.samples,
            samples=cleaned.activity.samples,
            report=cleaned.report,
        )
    )


def test_the_cut_classifies_every_labelled_ride_correctly(measured):
    """Eight waves kept, three artefacts refused, no exceptions.

    A ride with no speed reading is abstained on, and Miguel labelled that one a wave, so
    abstaining lands on the right answer here. It is still an absence of evidence rather
    than evidence, which is why it is called out separately below.
    """
    wrong = []
    for (start, _, is_wave, _), candidate in zip(LABELLED_SPANS, measured.candidates, strict=True):
        ratio = candidate.features.get("speed_corroboration")
        refused = ratio is not None and ratio < CUTOFF
        if refused == is_wave:
            wrong.append((start, is_wave, ratio))

    assert wrong == []


def test_the_measured_ratios_are_still_what_was_measured(measured):
    """A known-answer test. If L1 or L0.5 changes, these move and the cut is re-examined."""
    for (start, _, _, expected), candidate in zip(LABELLED_SPANS, measured.candidates, strict=True):
        ratio = candidate.features.get("speed_corroboration")
        if expected is None:
            assert ratio is None, f"span at {start} s gained a ratio it should not have"
        else:
            assert ratio == pytest.approx(expected, abs=0.02), f"span at {start} s"


def test_nothing_real_comes_close_to_the_cut_and_nothing_fake_comes_near_it(measured):
    """The plateau, restated as the property that makes the cutoff safe to pick.

    Real waves bottom out at 0.79 and artefacts top out at 0.38, so any cutoff between them
    gives the same eleven answers. The gap is what this asserts; 0.65 only has to sit in it.
    """
    real, fake = [], []
    for (_, _, is_wave, _), candidate in zip(LABELLED_SPANS, measured.candidates, strict=True):
        ratio = candidate.features.get("speed_corroboration")
        if ratio is not None:
            (real if is_wave else fake).append(ratio)

    assert min(real) > max(fake)
    assert min(PLATEAU) > max(fake)
    assert max(PLATEAU) < min(real)


def test_the_ride_the_watch_missed_entirely_gains_no_speed_claim(measured):
    """Ride 2: three seconds, no fix, no speed reading. A wave with nothing to publish.

    It survives by abstention, which is the honest outcome and not a measurement. What must
    not happen is that it acquires numbers it has not got.
    """
    index = next(i for i, (*_, ratio) in enumerate(LABELLED_SPANS) if ratio is None)
    features = measured.candidates[index].features

    assert "speed_corroboration" not in features
    assert "device_speed_max_ms" not in features
    assert "measured_speed_max_ms" not in features


def test_the_cleaner_had_already_refused_fixes_inside_both_bridged_artefacts(measured):
    """L0.5's own record convicts two of the three, and misses the slow one.

    That is exactly why it is reported and does not gate: perfect corroboration, useless as
    the test. Before ADR-0023 nothing downstream read it at all.
    """
    rejections = [
        candidate.features.get("rejected_fixes_in_span", 0.0) for candidate in measured.candidates
    ]
    bridged = [rejections[6], rejections[9]]
    everything_else = [r for i, r in enumerate(rejections) if i not in (6, 9)]

    assert all(r > 0 for r in bridged)
    assert everything_else == [0.0] * len(everything_else)


def test_the_reference_session_reports_eight_waves(sample_fit: Path):
    """End to end through the real chain, at the cutoff that ships.

    This is the number the product will show, and the one PLAN.md predicts.
    """
    cleaned = CleanStage().run(parse_file(sample_fit))
    track = KinematicsStage().run(cleaned.activity)
    framed = FrameStage().run(track)
    proposed = CandidateStage().run(framed)
    measured = FeatureStage().run(
        FeatureInput(
            candidates=proposed,
            framed=framed.samples,
            samples=cleaned.activity.samples,
            report=cleaned.report,
        )
    )

    before = ClassifyStage(min_speed_corroboration=0.0).run(measured)
    after = ClassifyStage(min_speed_corroboration=CUTOFF).run(measured)

    assert before.wave_count == 11
    assert after.wave_count == EXPECTED_WAVES == 8
    for cutoff in PLATEAU:
        assert ClassifyStage(min_speed_corroboration=cutoff).run(measured).wave_count == 8


# -- where the cutoff comes from ----------------------------------------------------------


def test_the_code_default_and_the_env_default_are_the_same_number():
    """The repo has to be able to reproduce its own published numbers with no ``.env``.

    That only holds if the shipped default lives in the stage and the settings field merely
    restates it. If these two ever drift, a clean checkout and a configured one disagree
    about the wave count with nothing on screen to say why.
    """
    declared = Settings.model_fields["wave_speed_corroboration"].default

    assert ClassifyStage().min_speed_corroboration == pytest.approx(declared)
    assert declared == pytest.approx(CUTOFF)


def test_the_environment_can_override_the_cutoff(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SURF_WAVE_SPEED_CORROBORATION", "0.5")

    assert Settings().wave_speed_corroboration == pytest.approx(0.5)


def test_a_cutoff_that_cannot_mean_anything_is_refused(monkeypatch: pytest.MonkeyPatch):
    """A ratio above 1.0 would refuse every candidate ever proposed; zero would refuse none."""
    for bad in ("0", "-0.2", "1.5"):
        monkeypatch.setenv("SURF_WAVE_SPEED_CORROBORATION", bad)
        with pytest.raises(ValidationError):
            Settings()


def test_a_configured_cutoff_reaches_the_stage_key(monkeypatch: pytest.MonkeyPatch):
    """The resolved value, not the default, is what a cached verdict is keyed on."""
    monkeypatch.setenv("SURF_WAVE_SPEED_CORROBORATION", "0.5")

    stage = ClassifyStage(min_speed_corroboration=Settings().wave_speed_corroboration)

    assert stage.meta.params["min_speed_corroboration"] == pytest.approx(0.5)
    assert stage.meta.params != ClassifyStage().meta.params
