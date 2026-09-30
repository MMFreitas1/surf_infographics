"""L4 -- features: what each of L3's proposals actually looks like, as numbers.

L3 proposes generously and judges nothing. This stage measures each proposal so that L5 can
judge it, and it measures from **every channel the watch recorded**, not just position.

That last point is the whole reason this stage looks the way it does. "51% of a session is
blind" is a fact about *position*. Measured on the reference file, heart rate, the odometer
and temperature are present for **100%** of blind seconds -- what is missing is the fix, not
the recording. A candidate the smoother had to estimate is not a candidate about which
nothing is known.

**The odometer is a window total, not a rate.** The device freezes its distance field for the
length of a blind window and back-fills the whole thing in one step when the fix returns:
every intra-window delta is 0.00 m, and the reference session's largest single step is
201.5 m. Read as a per-second speed that is 201 m/s, which is exactly the artefact Phase 5
spent two passes convicting (ADR-0014). So nothing here ever divides a back-fill step by one
second. What it does instead is attribute the step to the blind run it belongs to and report
that run's **average over its own duration**, which is the only rate the data supports. No
within-window structure is invented, because none was measured.

**A missing channel is an absent key, never a zero.** A GPX with no distance field yields no
odometer features at all rather than features reading 0.0 -- zero metres means "did not
move", which is a claim, and a different one. Anything consuming these has to handle the key
not being there; that is deliberate, and `SessionWindow` already documents the same rule.

Nothing here decides anything. `score` stays `None` and `direction` stays `UNKNOWN` through
this stage exactly as they do through L3 -- L5 is where a verdict is reached.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

import pyarrow as pa
import pyarrow.parquet as pq

from surf.models import FramedSample, RideDirection, Sample, SessionFrame, WaveCandidate
from surf.pipeline.l3 import CandidateSet
from surf.pipeline.stage import StageMeta

NAME = "L4"
"""Feature extraction is stage L4."""

CODE_VERSION = "1"
"""Bump when a feature changes meaning, so cached rows are not reused under a new definition."""

_COLUMNS = ("t_start", "t_end", "position_coverage")
_FEATURES_KEY = b"surf.l4.frame"

_FROZEN_M = 0.5
"""At or below this, a blind run recorded no movement at all.

Not a tuning knob so much as a floor: the reference session has 59 of 127 blind runs sitting
under it -- the surfer waiting for a set, wrist under water, going nowhere. A candidate whose
blind seconds are all frozen is one L5 can refuse without any further argument.
"""


class PayloadError(RuntimeError):
    """A cached payload is not something this stage wrote."""


@dataclass(frozen=True)
class FeatureInput:
    """What L4 needs: L3's proposals, the track they came from, and the raw channels.

    Three inputs rather than one because the proposals and the smoothed track carry no heart
    rate and no odometer, and those are precisely the channels that survive a blind window.
    Keyed on L3's key regardless, so the chain rule in `pipeline/session.py` still holds.
    """

    candidates: CandidateSet
    framed: Sequence[FramedSample]
    samples: Sequence[Sample]
    """The **cleaned** session's samples. L0.5 never touches ``distance_m`` -- it only reads
    it as corroboration -- so the odometer arrives here exactly as the device wrote it."""


@dataclass(frozen=True)
class FeatureSet:
    """L4's output: the same proposals, now measured, and the frame they were measured in."""

    frame: SessionFrame
    candidates: list[WaveCandidate]


@dataclass(frozen=True)
class BlindRun:
    """A stretch with no fix, and the distance the odometer back-filled for it.

    ``metres`` is ``None`` when the run is still open at the end of the recording: the
    catch-up step never arrived, so the distance is unknown rather than zero.
    """

    t_start: float
    t_end: float
    metres: float | None

    @property
    def duration_s(self) -> float:
        """How long the watch had no fix. What `blind_run_s` reports."""
        return self.t_end - self.t_start

    @property
    def covered_s(self) -> float:
        """How many seconds of travel this run's total actually accounts for.

        One more than the run is long, and the difference matters on a short run. The
        odometer was last correct at the second *before* the run began and is correct again
        at ``t_end``, so the total spans ``t_end - (t_start - 1)`` seconds -- including the
        step into the second the fix returned. Dividing by ``duration_s`` instead inflates
        the rate, and then paying that inflated rate to the catch-up second as well
        double-counts it.
        """
        return self.duration_s + 1.0

    @property
    def rate_ms(self) -> float | None:
        """Metres per second across the seconds this run accounts for. An average, always."""
        if self.metres is None or self.covered_s <= 0.0:
            return None
        return self.metres / self.covered_s

    @property
    def frozen(self) -> bool:
        """True when the watch recorded no movement across the whole run."""
        return self.metres is not None and self.metres <= _FROZEN_M


def blind_runs(samples: Sequence[Sample]) -> list[BlindRun]:
    """Every run of unpositioned seconds, with the distance its catch-up step carried.

    The catch-up lands on the second the fix returns, so a run's distance is the odometer
    reading there minus the reading at the last second before the run began -- the frozen
    value it held throughout.
    """
    runs: list[BlindRun] = []
    start: float | None = None
    before: float | None = None

    for index, sample in enumerate(samples):
        if not sample.has_position:
            if start is None:
                start = sample.t
                previous = samples[index - 1] if index else None
                before = previous.distance_m if previous is not None else None
            continue
        if start is not None:
            after = sample.distance_m
            metres = None if after is None or before is None else max(0.0, after - before)
            runs.append(BlindRun(t_start=start, t_end=sample.t, metres=metres))
            start = None

    if start is not None:
        # The recording ended with the fix still gone. No catch-up step ever arrived, so the
        # distance is unknown -- reporting 0.0 here would claim the surfer stopped moving.
        runs.append(BlindRun(t_start=start, t_end=samples[-1].t + 1.0, metres=None))
    return runs


def _overlap_s(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """Seconds two intervals share."""
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


@dataclass(frozen=True)
class FeatureStage:
    """L4: measure every proposal against every channel that recorded it."""

    recovery_s: float = 30.0
    """How long after a ride to look for the heart-rate drop that follows one.

    A ride ends in a kick-out and a rest; paddling does not. Thirty seconds is long enough
    for the drop to show at the 1 Hz this device records and short enough not to run into
    the next wave's paddling on a busy session.
    """
    takeoff_s: float = 4.0
    """The onset window the drop is looked for in. The synthetic's take-offs are 3-5 s."""
    peak_window_s: float = 10.0
    """The stretch `odometer_peak_ms` averages over.

    Near the length of a ride -- the synthetic's are 6-18 s and the reference session's
    proposals run 3-48 s -- so the window is long enough not to catch a single noisy second
    and short enough to survive being buried in an over-long proposal.
    """

    @property
    def meta(self) -> StageMeta:
        """Stage identity. Both params move the numbers, so both are in the key."""
        return StageMeta(
            name=NAME,
            code_version=CODE_VERSION,
            params={
                "recovery_s": self.recovery_s,
                "takeoff_s": self.takeoff_s,
                "peak_window_s": self.peak_window_s,
            },
        )

    def run(self, data: FeatureInput) -> FeatureSet:
        """Measure each candidate. Order and boundaries are L3's and are never changed."""
        runs = blind_runs(data.samples)
        return FeatureSet(
            frame=data.candidates.frame,
            candidates=[
                candidate.model_copy(update={"features": self._features(candidate, data, runs)})
                for candidate in data.candidates.candidates
            ],
        )

    def _features(
        self, candidate: WaveCandidate, data: FeatureInput, runs: Sequence[BlindRun]
    ) -> dict[str, float]:
        """Every number L5 gets to reason from, for one proposal."""
        start, end = candidate.t_start, candidate.t_end
        features: dict[str, float] = {
            "duration_s": candidate.duration_s,
            "position_coverage": candidate.position_coverage,
        }
        features.update(self._kinematics(data.framed, start, end))
        features.update(self._odometer(runs, start, end))
        features.update(self._attributed_odometer(data.samples, runs, start, end))
        features.update(self._heart_rate(data.samples, start, end))
        return features

    def _attributed_odometer(
        self, samples: Sequence[Sample], runs: Sequence[BlindRun], start: float, end: float
    ) -> dict[str, float]:
        """How far the surfer travelled during *this candidate*, second by second.

        The sharpest odometer signal available, and the one the run-level features cannot
        give: `blind_run_mean_ms` averages over a whole blind stretch, so a ten-second ride
        inside a hundred-second stretch comes back at paddling pace.

        Every second of the candidate is attributed exactly once, from one of two places:

        * **an observed second** contributes its own odometer delta, which is a real
          per-second measurement. Catch-up steps are excluded here by construction -- a step
          whose previous sample had no fix belongs to the run before it, not to the second it
          landed on, which is what stops 201 metres from being read as one second of travel.
        * **a blind second** contributes its run's average, because the run's total is all
          the device recorded and spreading it evenly is the only assumption that adds
          nothing. It is an average and is named one; no peak is ever claimed from it.

        Reading the span's endpoints instead would have been simpler and wrong: a ride
        normally *ends* with the wrist going under, so its trailing run back-fills after
        `t_end` and an endpoint reading undercounts exactly the candidates that matter most.
        """
        duration = end - start
        if duration <= 0.0:
            return {}

        per_second = self._per_second_metres(samples, runs, start, end)
        if not per_second:
            return {}

        metres = sum(per_second)
        out = {"odometer_m": metres, "odometer_ms": metres / duration}

        # The best sustained stretch inside the candidate, not the candidate's own mean.
        # L3 merges bursts separated by less than its gap, so a real 15 s ride routinely
        # arrives inside a 40 s proposal padded with paddling either side -- and a mean over
        # the whole proposal reads as paddling, which is what the padding was. Measured on
        # the five seeded sessions, that dilution was the single largest source of refused
        # rides. Still an average, over a fixed window, so no peak is ever claimed.
        window = int(min(self.peak_window_s, len(per_second)))
        if window > 0:
            best = max(sum(per_second[i : i + window]) for i in range(len(per_second) - window + 1))
            out["odometer_peak_ms"] = best / window
        return out

    def _per_second_metres(
        self, samples: Sequence[Sample], runs: Sequence[BlindRun], start: float, end: float
    ) -> list[float]:
        """Metres travelled in each second of the candidate, attributed exactly once.

        An observed second takes its own odometer delta -- a real per-second measurement. A
        blind second takes its run's average, because the run's total is all the device
        recorded and spreading it evenly assumes the least. The second the fix *returns*
        takes the run's average too: the step landing on it belongs to the run behind it, not
        to that second, which is what stops 201 metres from becoming 201 m/s.
        """
        rates = {
            (run.t_start, run.t_end): rate for run in runs if (rate := run.rate_ms) is not None
        }

        def rate_at(t: float) -> float | None:
            for (run_start, run_end), rate in rates.items():
                if run_start <= t < run_end:
                    return rate
            return None

        metres: list[float] = []
        known = False
        for previous, current in pairwise(samples):
            if not (start <= current.t < end):
                continue
            if not current.has_position:
                rate = rate_at(current.t)
            elif previous.has_position:
                rate = (
                    max(0.0, current.distance_m - previous.distance_m)
                    if current.distance_m is not None and previous.distance_m is not None
                    else None
                )
            else:
                # The second the fix came back. Its step carries the whole run behind it.
                rate = rate_at(previous.t)
            if rate is not None:
                known = True
            metres.append(rate or 0.0)
        return metres if known else []

    def _kinematics(
        self, framed: Sequence[FramedSample], start: float, end: float
    ) -> dict[str, float]:
        """Shape features from the track: how fast, how steady, how hard the drop.

        Speed statistics are taken over **observed** seconds only. The smoother estimates
        every second by design (ADR-0010), but an estimate's variance is a property of the
        filter rather than of the surfing, and the latched-reading test below would read it
        as suspiciously smooth.
        """
        during = [s for s in framed if start <= s.t < end]
        if not during:
            return {}

        out: dict[str, float] = {
            "sustained_shoreward_s": float(sum(1 for s in during if s.v_cross_ms > 0.0)),
        }

        observed = [s.speed_ms for s in during if s.observed]
        if observed:
            out["measured_speed_max_ms"] = max(observed)
            out["measured_speed_mean_ms"] = statistics.fmean(observed)
        if len(observed) > 1:
            # Near-zero variance across many seconds is a stale latched reading, not a ride.
            out["measured_speed_variance"] = statistics.variance(observed)

        onset = [s for s in during if s.t < start + self.takeoff_s]
        if len(onset) > 1:
            steps = [
                (b.v_cross_ms - a.v_cross_ms) / (b.t - a.t) for a, b in pairwise(onset) if b.t > a.t
            ]
            if steps:
                out["takeoff_accel_ms2"] = max(steps)
        return out

    def _odometer(self, runs: Sequence[BlindRun], start: float, end: float) -> dict[str, float]:
        """What the device's own distance field says about this proposal's blind seconds.

        Reported per blind *run*, never per second. A run's metres are a total the watch
        back-filled in one step, so the only honest rate is that total over the run's own
        duration -- and even that is an average, which is why it is named one.

        ``blind_overlap_s`` is how much of the candidate sits inside those runs, kept
        separate from the runs' own duration so that a proposal clipping the edge of a long
        blind stretch cannot be read as one that spans it.
        """
        touching = [run for run in runs if _overlap_s(start, end, run.t_start, run.t_end) > 0.0]
        if not touching:
            return {}

        overlap = sum(_overlap_s(start, end, r.t_start, r.t_end) for r in touching)
        out: dict[str, float] = {"blind_overlap_s": overlap}

        measured = [run for run in touching if run.metres is not None]
        if not measured:
            # Every run touching this candidate is still open at the end of the recording.
            # There is no distance to report, and 0.0 would be a claim that there was none.
            return out

        metres = sum(run.metres or 0.0 for run in measured)
        out["blind_run_m"] = metres
        out["blind_run_s"] = sum(run.duration_s for run in measured)
        covered = sum(run.covered_s for run in measured)
        if covered > 0.0:
            # Over the seconds the totals account for, not over the blind span -- see
            # BlindRun.covered_s. On a short run the two differ materially.
            out["blind_run_mean_ms"] = metres / covered
        out["frozen_blind_s"] = sum(
            _overlap_s(start, end, r.t_start, r.t_end) for r in measured if r.frozen
        )
        return out

    def _heart_rate(self, samples: Sequence[Sample], start: float, end: float) -> dict[str, float]:
        """The one channel with no gaps, and the recovery drop that follows a real ride.

        A ride is paddle, drop, ride, then rest. The rest is the part a blind window cannot
        hide: heart rate keeps recording underwater, so a falling rate after the proposal is
        evidence available even where position is not.
        """
        during = [s.hr_bpm for s in samples if start <= s.t < end and s.hr_bpm is not None]
        if not during:
            return {}

        out: dict[str, float] = {
            "hr_mean_bpm": statistics.fmean(during),
            "hr_max_bpm": float(max(during)),
            "hr_at_start_bpm": float(during[0]),
        }
        after = [
            s.hr_bpm for s in samples if end <= s.t < end + self.recovery_s and s.hr_bpm is not None
        ]
        mean_after = _mean([float(v) for v in after])
        if mean_after is not None:
            # Negative means the rate fell after the proposal ended, which is what a ride
            # followed by a rest looks like.
            out["hr_delta_after_bpm"] = mean_after - out["hr_mean_bpm"]
        return out

    def encode(self, output: FeatureSet) -> bytes:
        """Serialise the measured proposals, frame as metadata -- L3's shape, plus features."""
        columns: dict[str, pa.Array] = {
            name: pa.array([getattr(c, name) for c in output.candidates], type=pa.float64())
            for name in _COLUMNS
        }
        columns["score"] = pa.array([c.score for c in output.candidates], type=pa.float64())
        columns["direction"] = pa.array(
            [c.direction.value for c in output.candidates], type=pa.string()
        )
        columns["features"] = pa.array(
            [json.dumps(c.features, sort_keys=True) for c in output.candidates],
            type=pa.string(),
        )
        table = pa.table(columns).replace_schema_metadata(
            {_FEATURES_KEY: output.frame.model_dump_json().encode("utf-8")}
        )
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="zstd")
        return bytes(sink.getvalue().to_pybytes())

    def decode(self, payload: bytes) -> FeatureSet:
        """Rebuild the feature set ``encode`` wrote, frame included."""
        table = pq.read_table(pa.BufferReader(payload))
        raw = (table.schema.metadata or {}).get(_FEATURES_KEY)
        if raw is None:
            msg = f"{NAME} payload carries no frame metadata: it was not written by this stage"
            raise PayloadError(msg)
        return FeatureSet(
            frame=SessionFrame(**json.loads(raw)),
            candidates=[
                WaveCandidate(
                    t_start=row["t_start"],
                    t_end=row["t_end"],
                    position_coverage=row["position_coverage"],
                    score=row["score"],
                    direction=RideDirection(row["direction"]),
                    features=json.loads(row["features"]),
                )
                for row in table.to_pylist()
            ],
        )
