"""Synthetic surf sessions with exactly known ground truth.

Two kinds of truth come out of here, and they answer different questions. ``truth`` is the
list of intervals that are genuinely rides -- what a *detector* is scored against.
``true_track`` is the noiseless position and velocity per second, before dropout and GPS
noise -- what a *smoother* is scored against.

Why this exists: the detector needs something to be measured against before human labels
exist, and we deliberately take no dependency on any third-party app's output (ADR-0008).
A generated session gives exact truth, contains no personal location data, and is
reproducible from a seed.

The dropout process is deliberately *independent of activity state*. It is plausible that
GPS recovers during a ride, because the rider is standing with the wrist clear of the
water -- but that is an untested hypothesis, and baking it into the fixture would let a
detector score well by learning an assumption rather than the signal.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from surf.evaluation import Interval
from surf.models import Activity, BlindCause, BlindWindow, Fidelity, Sample

ORIGIN_LAT = 38.0
ORIGIN_LON = -9.0
"""A neutral offshore origin. Not anyone's home break."""

M_PER_DEG_LAT = 111_320.0


@dataclass(frozen=True)
class SyntheticParams:
    """Knobs for the generator. Defaults produce a realistic ~50%-coverage session."""

    seed: int = 7
    n_waves: int = 8
    paddle_out_s: tuple[int, int] = (45, 90)
    wait_s: tuple[int, int] = (60, 200)
    takeoff_s: tuple[int, int] = (3, 5)
    ride_s: tuple[int, int] = (6, 18)
    recover_s: tuple[int, int] = (12, 30)
    paddle_speed: float = 1.0
    ride_peak_speed: tuple[float, float] = (4.0, 8.0)
    gps_noise_m: float = 3.0
    p_lose_fix: float = 0.045
    """Per-second chance of losing the fix while holding one."""
    p_regain_fix: float = 0.05
    """Per-second chance of regaining the fix while lost."""
    walk_out_s: int = 0
    """Seconds of walking up the beach to append after the last ride. 0 appends nothing.

    Off by default, and that is not timidity: every committed golden and most of the test
    suite is built on this generator's default output, so a default that produced a
    different session would move all of them at once.
    """
    idle_s: int = 0
    """Seconds of standing still with the watch running, after the walk."""
    walk_speed: float = 1.3
    """Walking pace, m/s. Brisk enough to be motion, far too slow to be a ride."""
    break_after_wave: int = 0
    """Splice a stretch out of the water in after this wave number. 0 splices nothing.

    The surfer comes in, sits on the sand, and paddles back out. This is the case the
    deterministic baseline cannot catch by construction -- it only trims the ends, because
    an interior dry spell is far more likely to be someone sitting up on their board
    (ADR-0015) -- so it is the only truth against which an audit pass can prove it adds
    anything at all.
    """
    break_s: int = 0
    """How long that interior break lasts, in seconds."""
    odometer: bool = False
    """Record a ``distance_m`` that behaves like the device's own, gaps included.

    Off by default for the same reason ``walk_out_s`` is: every committed golden is built on
    this generator's default output, and a default that produced a different session would
    move all of them at once.

    What it models is not a clean integral. Measured on the reference FIT, the watch's
    odometer **freezes** for the length of a blind window and then back-fills the whole
    distance in a single step on the second it regains a fix -- every intra-window delta is
    0.00 m, and one window lands 201.5 m in one second. That single step is where Phase 5's
    impossible speeds come from, so any stage reading this field has to read it as a window
    total and never as a per-second speed. A resolver tested against a smoothly integrated
    odometer would be tested against a signal that does not exist.
    """


@dataclass(frozen=True)
class TrueState:
    """One second of the noiseless state the generator integrated.

    This is the track *before* dropout and GPS noise were applied -- what a perfect
    smoother would recover. Exposing it is what makes L1 measurable: without it there is
    nothing to compare a recovered track against, and "the smoother works" stays an
    eyeball claim.
    """

    t: float
    x_m: float
    """Metres east of the origin. Shore lies to the east, so rides travel in +x."""
    y_m: float
    """Metres north of the origin."""
    vx_ms: float
    vy_ms: float

    @property
    def speed_ms(self) -> float:
        """True ground speed, the value a positioned sample records."""
        return math.hypot(self.vx_ms, self.vy_ms)

    @property
    def lat_lon(self) -> tuple[float, float]:
        """The same point in degrees, for comparing against a sample directly."""
        return _to_latlon(self.x_m, self.y_m)


@dataclass(frozen=True)
class SyntheticSession:
    """A generated session, the intervals that are genuinely rides, and the true track."""

    activity: Activity
    truth: list[Interval] = field(default_factory=list)
    true_track: list[TrueState] = field(default_factory=list)
    """The noiseless state per second, index-aligned with ``activity.samples``."""
    out_of_water: list[Interval] = field(default_factory=list)
    """Intervals the surfer spent out of the water, exactly known.

    Empty unless the session was asked for one. This is the truth L0.6 is scored against,
    and it is the only place that truth can come from: nobody can mark from memory which
    minute they walked out of the sea, which is the same problem ADR-0013 records for waves.

    Boundary stretches and interior breaks land in the same list on purpose, so a scorer
    reads one field and does not have to know which kind of absence it is looking at.
    """

    @property
    def interior_breaks(self) -> list[Interval]:
        """The out-of-water stretches that are not at either end of the recording.

        What separates the two contenders: the baseline scores zero recall here by
        construction, so this is where an audit pass has to earn its keep.
        """
        if not self.true_track and not self.activity.samples:
            return []
        first = self.activity.samples[0].t
        last = self.activity.samples[-1].t
        return [iv for iv in self.out_of_water if iv.t_start > first and iv.t_end < last]

    @property
    def wave_count(self) -> int:
        """Number of real rides in this session."""
        return len(self.truth)


def _to_latlon(x_m: float, y_m: float) -> tuple[float, float]:
    """Local metres east/north to degrees, at the synthetic origin."""
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))
    return ORIGIN_LAT + y_m / M_PER_DEG_LAT, ORIGIN_LON + x_m / m_per_deg_lon


def make_synthetic_session(params: SyntheticParams | None = None) -> SyntheticSession:
    """Build a deterministic session: paddle out, wait, take off, ride, recover, repeat.

    Shore lies to the east, so rides travel in +x and paddle-outs in -x.
    """
    p = params or SyntheticParams()
    rng = random.Random(p.seed)

    # -- build the true velocity profile second by second -------------------------
    velocities: list[tuple[float, float]] = []  # (vx east, vy north) m/s
    truth_spans: list[tuple[int, int]] = []

    for _ in range(p.n_waves):
        for _ in range(rng.randint(*p.paddle_out_s)):
            velocities.append((-p.paddle_speed, rng.uniform(-0.15, 0.15)))
        for _ in range(rng.randint(*p.wait_s)):
            velocities.append((rng.uniform(-0.2, 0.2), rng.uniform(-0.25, 0.25)))
        for _ in range(rng.randint(*p.takeoff_s)):
            velocities.append((rng.uniform(1.2, 2.4), rng.uniform(-0.3, 0.3)))

        ride_len = rng.randint(*p.ride_s)
        peak = rng.uniform(*p.ride_peak_speed)
        lateral = rng.choice((-1.0, 1.0)) * rng.uniform(0.3, 1.4)
        start = len(velocities)
        for i in range(ride_len):
            # accelerate hard on the drop, bleed off toward the kick-out
            phase = (i + 1) / ride_len
            ride_speed = peak * math.sin(math.pi * min(1.0, phase * 1.15)) ** 0.5
            velocities.append((max(ride_speed, 0.5), lateral * ride_speed / peak))
        truth_spans.append((start, len(velocities)))

        for _ in range(rng.randint(*p.recover_s)):
            velocities.append((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3)))

    # -- integrate to positions, apply dropout and noise ---------------------------
    samples: list[Sample] = []
    steps: list[float] = []
    """Ground distance covered in each second, index-aligned with ``samples``.

    Carried separately because the odometer has to know how far the surfer moved during a
    blind window, and the sample recorded for that second deliberately does not.
    """
    blind: list[BlindWindow] = []
    true_track: list[TrueState] = []
    x = y = 0.0
    has_fix = True
    gap_start: float | None = None

    lat: float | None
    lon: float | None
    speed: float | None

    for t, (vx, vy) in enumerate(velocities):
        x += vx
        y += vy
        # Recorded before any noise or dropout, and drawing no random numbers: the golden
        # depends on the RNG sequence, so anything added here must not consume from it.
        true_track.append(TrueState(t=float(t), x_m=x, y_m=y, vx_ms=vx, vy_ms=vy))

        has_fix = rng.random() >= p.p_lose_fix if has_fix else rng.random() < p.p_regain_fix

        if has_fix:
            if gap_start is not None:
                blind.append(
                    BlindWindow(t_start=gap_start, t_end=float(t), cause=BlindCause.NO_FIX)
                )
                gap_start = None
            lat, lon = _to_latlon(
                x + rng.gauss(0.0, p.gps_noise_m), y + rng.gauss(0.0, p.gps_noise_m)
            )
            speed = math.hypot(vx, vy)
        else:
            if gap_start is None:
                gap_start = float(t)
            lat = None
            lon = None
            speed = None

        samples.append(
            Sample(
                t=float(t),
                lat=lat,
                lon=lon,
                speed_ms=speed,
                hr_bpm=int(95 + 25 * math.hypot(vx, vy) / 8.0 + rng.gauss(0.0, 3.0)),
                distance_m=None,
            )
        )
        steps.append(math.hypot(vx, vy))

    if gap_start is not None:
        blind.append(
            BlindWindow(t_start=gap_start, t_end=float(len(velocities)), cause=BlindCause.NO_FIX)
        )

    # -- the walk up the beach, if one was asked for ------------------------------
    # Appended after every draw above, from its own generator, so that switching it on
    # cannot shift a single sample of the session that precedes it. The committed golden
    # depends on the RNG sequence, and this is how that promise is kept.
    out_of_water: list[Interval] = []
    if p.walk_out_s or p.idle_s:
        dry = random.Random(p.seed + 1)
        dry_start = float(len(velocities))
        for _ in range(p.walk_out_s):
            x += p.walk_speed
            y += dry.uniform(-0.1, 0.1)
            samples.append(_dry_sample(float(len(samples)), x, y, p.walk_speed, dry))
            steps.append(p.walk_speed)
        for _ in range(p.idle_s):
            samples.append(_dry_sample(float(len(samples)), x, y, 0.0, dry))
            steps.append(0.0)
        out_of_water.append(Interval(dry_start, float(len(samples))))

    # -- the interior break, if one was asked for ---------------------------------
    # Spliced after the fact rather than woven into the loop above, and from its own
    # generator, for the same reason the tail is: switching it on must not shift a single
    # random draw of the session it interrupts.
    if p.break_after_wave and p.break_s:
        samples, steps, truth_spans, out_of_water = _splice_break(
            p, samples, steps, truth_spans, out_of_water
        )

    # -- the odometer, if one was asked for ---------------------------------------
    # Last, so that it sees the spliced session rather than the one before the splice, and
    # deterministic: it draws no random numbers at all, so switching it on cannot move a
    # single sample of a session generated without it.
    if p.odometer:
        samples = _apply_odometer(samples, steps)

    activity = Activity(
        activity_id=f"synthetic-{p.seed}",
        sport="surfing",
        start_time=0.0,
        fidelity=Fidelity.FIT,
        samples=samples,
        blind_windows=blind,
        device="synthetic",
        source_file="",
    )
    return SyntheticSession(
        activity=activity,
        truth=[Interval(float(a), float(b)) for a, b in truth_spans],
        true_track=true_track,
        out_of_water=out_of_water,
    )


def _splice_break(
    p: SyntheticParams,
    samples: list[Sample],
    steps: list[float],
    truth_spans: list[tuple[int, int]],
    out_of_water: list[Interval],
) -> tuple[list[Sample], list[float], list[tuple[int, int]], list[Interval]]:
    """Insert a stretch on dry land after one wave, sliding everything after it later.

    The surfer rides in, sits on the sand, and paddles back out. Everything downstream of
    the splice -- samples, per-second distances, ride truth, the tail's own interval -- moves
    by the length of the break, because a session cannot have two seconds numbered the same.
    """
    index = min(p.break_after_wave, len(truth_spans)) - 1
    if index < 0:
        return samples, steps, truth_spans, out_of_water

    at = truth_spans[index][1]
    dry = random.Random(p.seed + 2)
    origin = samples[at - 1] if at else samples[0]
    x, y = _to_metres(origin.lat, origin.lon)

    inserted: list[Sample] = []
    inserted_steps: list[float] = []
    for step in range(p.break_s):
        # walk up the beach for the first fifth of it, then sit down
        moving = step < max(1, p.break_s // 5)
        if moving:
            x += p.walk_speed
        inserted.append(_dry_sample(float(at + step), x, y, p.walk_speed if moving else 0.0, dry))
        inserted_steps.append(p.walk_speed if moving else 0.0)

    shifted = [s.model_copy(update={"t": s.t + p.break_s}) for s in samples[at:]]
    return (
        samples[:at] + inserted + shifted,
        steps[:at] + inserted_steps + steps[at:],
        [(a, b) if b <= at else (a + p.break_s, b + p.break_s) for a, b in truth_spans],
        [Interval(float(at), float(at + p.break_s))]
        + [
            Interval(iv.t_start + p.break_s, iv.t_end + p.break_s) if iv.t_start >= at else iv
            for iv in out_of_water
        ],
    )


def _apply_odometer(samples: list[Sample], steps: list[float]) -> list[Sample]:
    """Write a ``distance_m`` that gaps the way the real device's does.

    The watch reports a cumulative distance every second, including seconds it has no fix
    for -- but while the fix is gone the number does not move. It catches up in one step on
    the second the fix returns, carrying the whole blind window's distance with it.

    So the odometer is a **window total, not a rate**. Reading the catch-up step as one
    second of travel yields 201 m/s; that artefact is real, it is in the reference file, and
    a resolver has to survive it rather than be handed a signal that never gaps.

    Deliberately consumes no randomness: the golden sessions depend on the RNG sequence.
    """
    out: list[Sample] = []
    cumulative = 0.0
    pending = 0.0
    for sample, step in zip(samples, steps, strict=True):
        if sample.has_position:
            cumulative += pending + step
            pending = 0.0
        else:
            # The fix is gone. Distance still accrues in the world; the watch just is not
            # writing it down yet, so it rides along in ``pending`` until the fix returns.
            pending += step
        out.append(sample.model_copy(update={"distance_m": cumulative}))
    return out


def _to_metres(lat: float | None, lon: float | None) -> tuple[float, float]:
    """Degrees back to the local metres the generator integrates in."""
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))
    return ((lon or ORIGIN_LON) - ORIGIN_LON) * m_per_deg_lon, (
        (lat or ORIGIN_LAT) - ORIGIN_LAT
    ) * M_PER_DEG_LAT


def _dry_sample(t: float, x: float, y: float, speed: float, rng: random.Random) -> Sample:
    """One second with the watch out of the water.

    Always positioned, and that is the whole signal. Dropout in this generator models a
    submerged wrist; on land there is nothing between the watch and the sky, so coverage
    goes to 1.0 exactly where speed goes to nothing. Heart rate stays elevated, because
    someone who has just surfed for an hour is still breathing hard while they walk.
    """
    lat, lon = _to_latlon(x + rng.gauss(0.0, 2.0), y + rng.gauss(0.0, 2.0))
    return Sample(
        t=t,
        lat=lat,
        lon=lon,
        speed_ms=max(0.0, speed + rng.gauss(0.0, 0.1)),
        hr_bpm=int(105 + rng.gauss(0.0, 4.0)),
        distance_m=None,
    )
