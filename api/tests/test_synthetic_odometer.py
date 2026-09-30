"""The synthetic generator's odometer, and the artefact it exists to reproduce.

A resolver that reads the device's distance field has to be tested against a field that
behaves like the device's. Measured on the reference FIT, that behaviour is not a clean
integral: the odometer **freezes** for the length of a blind window and back-fills the whole
distance in one step on the second the fix returns. Every intra-window delta is 0.00 m; the
largest single step in the reference session is 201.5 m.

That step is the reason it matters. Read as one second of travel it is 201 m/s -- which is
exactly the class of impossible speed Phase 5 spent two passes convicting (ADR-0014). A
resolver handed a smoothly integrated odometer would never meet it, and would meet it for
the first time on real data.

The tests below pin both halves: that turning the odometer on changes nothing else about a
generated session, and that what it writes gaps the way the real one does.
"""

import hashlib
import json
from itertools import pairwise

import pytest

from surf.models import Sample
from surf.synthetic import SyntheticParams, _apply_odometer, make_synthetic_session


@pytest.fixture
def plain():
    """The default session: no odometer, the shape every committed golden is built on."""
    return make_synthetic_session()


@pytest.fixture
def metered():
    """The same session with the odometer switched on."""
    return make_synthetic_session(SyntheticParams(odometer=True))


def stream_digest(session) -> str:
    """A hash of every sample, so "nothing moved" is checked rather than asserted."""
    return hashlib.sha256(
        json.dumps([s.model_dump() for s in session.activity.samples], sort_keys=True).encode()
    ).hexdigest()


def blind_deltas(session) -> list[list[float]]:
    """Per-second odometer deltas inside each blind window, window by window."""
    by_t = {s.t: s for s in session.activity.samples}
    out = []
    for window in session.activity.blind_windows:
        seconds = [t for t in range(int(window.t_start), int(window.t_end) + 1) if t in by_t]
        deltas = [
            by_t[seconds[i]].distance_m - by_t[seconds[i - 1]].distance_m
            for i in range(1, len(seconds))
        ]
        if deltas:
            out.append(deltas)
    return out


def test_it_is_off_by_default(plain):
    """Every committed golden is built on the default output, so the default must not move."""
    assert all(s.distance_m is None for s in plain.activity.samples)


def test_switching_it_on_changes_nothing_but_the_distance(plain, metered):
    """The odometer draws no random numbers, so it cannot shift the session it measures.

    This is the property that lets the field be added at all: the RNG sequence is what every
    golden depends on, and a post-pass that consumed from it would move all of them.
    """
    assert len(plain.activity.samples) == len(metered.activity.samples)
    for before, after in zip(plain.activity.samples, metered.activity.samples, strict=True):
        assert before.model_dump(exclude={"distance_m"}) == after.model_dump(exclude={"distance_m"})
    assert plain.truth == metered.truth
    assert plain.activity.blind_windows == metered.activity.blind_windows


def test_the_default_stream_is_unchanged_by_the_feature_existing(plain):
    """A tripwire for the golden promise: this digest changes only if the default does."""
    assert stream_digest(plain) == (
        "597fd325edb9a6fd75b192cd19c34919ced2cb1661860d0ba81a9ae88dc27a49"
    )


def test_it_reports_a_distance_for_every_second_including_blind_ones(metered):
    """The real watch never stops reporting. It stops *changing*, which is a different thing.

    A null here would be a truthful "no data", and would therefore be the wrong fixture: the
    trap this reproduces is a number that is present, plausible and stale.
    """
    assert all(s.distance_m is not None for s in metered.activity.samples)


def test_it_never_goes_backwards(metered):
    distances = [s.distance_m for s in metered.activity.samples]
    assert all(b >= a for a, b in pairwise(distances))


def test_it_does_not_move_while_the_fix_is_gone(metered):
    """Inside a window, every delta but the catch-up is exactly zero."""
    windows = blind_deltas(metered)
    assert windows, "the default session should contain blind windows"
    for deltas in windows:
        assert all(d == pytest.approx(0.0) for d in deltas[:-1]), (
            "the odometer moved mid-window; the real one does not"
        )


def test_it_back_fills_the_whole_window_in_one_step(metered):
    """The catch-up step carries distance no single second could have covered.

    This is the artefact in one assertion: a step far larger than any plausible per-second
    travel, landing on the second the fix returns.
    """
    catch_ups = [deltas[-1] for deltas in blind_deltas(metered) if len(deltas) > 3]
    assert catch_ups
    assert max(catch_ups) > 20.0, "no step large enough to be a back-fill"


def test_the_total_is_the_distance_actually_travelled(metered):
    """Nothing is lost in a gap and nothing is invented to fill one.

    The generator integrates 1 m/s paddling, a ride peaking at 4-8 m/s and near-zero drift
    while waiting, so the total is bounded well away from both zero and absurdity.
    """
    total = metered.activity.samples[-1].distance_m
    seconds = len(metered.activity.samples)
    assert 0.1 < total / seconds < 3.0, f"{total:.0f} m over {seconds} s is not a surf session"


def test_a_window_with_no_movement_stays_frozen_and_back_fills_nothing():
    """The signal that settles a candidate outright: the surfer did not move at all.

    Built by hand because the generator's waiting drifts a little every second, while a real
    session sits genuinely still -- 59 of the reference file's 127 blind windows advance the
    odometer by 0.5 m or less. That case has to be pinned somewhere, and this is where.
    """
    samples = [
        Sample(t=0.0, lat=38.0, lon=-9.0),
        Sample(t=1.0),  # no fix
        Sample(t=2.0),  # no fix
        Sample(t=3.0),  # no fix
        Sample(t=4.0, lat=38.0, lon=-9.0),
    ]
    metered = _apply_odometer(samples, [1.0, 0.0, 0.0, 0.0, 0.0])

    assert [s.distance_m for s in metered] == [1.0, 1.0, 1.0, 1.0, 1.0]


def test_the_catch_up_lands_on_the_second_the_fix_returns():
    """Where the whole window's distance appears, to the second."""
    samples = [
        Sample(t=0.0, lat=38.0, lon=-9.0),
        Sample(t=1.0),
        Sample(t=2.0),
        Sample(t=3.0, lat=38.0, lon=-9.0),
    ]
    metered = _apply_odometer(samples, [0.0, 5.0, 6.0, 7.0])

    assert [s.distance_m for s in metered] == [0.0, 0.0, 0.0, 18.0]


def test_it_survives_the_interior_break_splice():
    """The break inserts seconds mid-session; the odometer must still be aligned after it."""
    session = make_synthetic_session(
        SyntheticParams(odometer=True, break_after_wave=3, break_s=120)
    )
    distances = [s.distance_m for s in session.activity.samples]

    assert len(distances) == len(session.activity.samples)
    assert all(d is not None for d in distances)
    assert all(b >= a for a, b in pairwise(distances))
