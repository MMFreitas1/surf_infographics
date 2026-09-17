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
    """

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
        for _ in range(p.idle_s):
            samples.append(_dry_sample(float(len(samples)), x, y, 0.0, dry))
        out_of_water.append(Interval(dry_start, float(len(samples))))

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
