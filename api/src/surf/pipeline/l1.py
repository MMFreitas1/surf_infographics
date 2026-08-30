"""L1 -- kinematics: a smoothed track with honest per-second confidence.

Offline smoothing is the product's technical edge (ADR-0003). A watch filters online and
only ever sees the past; we hold the whole session, so a Rauch-Tung-Striebel backward pass
refines every second using what came *after* it as well as before. That is also what gives
the uncertainty inside a gap its right shape: it peaks in the **middle** of an unobserved
stretch rather than at its end, because the track is pinned from both sides. A forward-only
filter cannot produce that curve, which makes it the sharpest evidence that the backward
pass actually ran.

The output is a parallel track (ADR-0010), never an overwrite of what was measured.

Two things this stage deliberately does not do:

* It emits one row per input sample. A second with no record at all -- a `MISSING_RECORD`
  window -- gets no row, because inventing one would be inventing data. Those windows stay
  on the `Activity` as first-class objects.
* It does not read `Activity.blind_windows`. Not because they are unwelcome, but because
  `Sample.has_position` is the same fact at finer grain, and the filter works per second.
  Nothing here re-derives a window.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from numpy.typing import NDArray

from surf.geo import LocalFrame
from surf.models import Activity, Sample, SmoothedSample
from surf.pipeline.stage import StageMeta

NAME = "L1"
"""Kinematics is stage L1."""

CODE_VERSION = "1"
"""Bump when the smoother changes what it produces, so cached tracks are not reused."""

_STATE = 4
"""State is [x, y, vx, vy]: position and velocity in the session's local metric frame."""

_COLUMNS = ("t", "lat", "lon", "vx_ms", "vy_ms", "position_sigma_m", "confidence")
_PARAMS_KEY = b"surf.l1.params"


def _transition(dt: float) -> NDArray[np.float64]:
    """Constant-velocity motion over ``dt`` seconds."""
    f = np.eye(_STATE)
    f[0, 2] = dt
    f[1, 3] = dt
    return f


def _process_noise(dt: float, q: float) -> NDArray[np.float64]:
    """Continuous white-noise acceleration, discretised. ``q`` is in m^2/s^3.

    This is the model's admission that a surfer accelerates: without it the filter would
    believe its own constant-velocity story and refuse to follow a take-off.
    """
    dt2 = dt * dt
    dt3 = dt2 * dt
    block = np.array([[dt3 / 3.0, dt2 / 2.0], [dt2 / 2.0, dt]])
    noise = np.zeros((_STATE, _STATE))
    for axis in (0, 1):
        idx = np.array([axis, axis + 2])
        noise[np.ix_(idx, idx)] = block
    return q * noise


@dataclass(frozen=True)
class _Filtered:
    """Everything the backward pass needs from the forward pass."""

    states: NDArray[np.float64]
    covariances: NDArray[np.float64]
    predicted_states: NDArray[np.float64]
    predicted_covariances: NDArray[np.float64]
    transitions: NDArray[np.float64]


@dataclass(frozen=True)
class KinematicsStage:
    """L1: Kalman filter plus RTS smoother over a session's samples.

    Every param here changes the track, so every one of them is in the cache key.
    """

    measurement_noise_m: float = 3.0
    """Standard deviation of a single GPS fix. The synthetic fixture is built at 3 m."""
    process_noise: float = 0.25
    """Acceleration intensity, m^2/s^3. Higher follows a take-off faster and trusts the
    fixes less. Chosen by sweeping against the synthetic true track, where it minimises both
    position and speed error -- see the sweep in this stage's tests. Tuned on generated
    motion, so revisit it once Phase 4 provides human labels on real sessions."""
    max_speed_ms: float = 12.0
    """ADR-0003's physical prior, applied where it belongs: a fix that would need more than
    this to reach from the last accepted one is not evidence about position. Raw differencing
    on the reference session reaches 109 m/s, and that is what this rejects."""
    outlier_variance_factor: float = 1e4
    """How hard a gated fix is discounted. Inflating its variance rather than dropping it
    means a *sustained* disagreement can still pull the track, while a lone spike cannot."""
    confidence_sigma_m: float = 10.0
    """Position uncertainty at which confidence is one half."""

    @property
    def meta(self) -> StageMeta:
        """Stage identity."""
        return StageMeta(
            name=NAME,
            code_version=CODE_VERSION,
            params={
                "measurement_noise_m": self.measurement_noise_m,
                "process_noise": self.process_noise,
                "max_speed_ms": self.max_speed_ms,
                "outlier_variance_factor": self.outlier_variance_factor,
                "confidence_sigma_m": self.confidence_sigma_m,
            },
        )

    def run(self, data: Activity) -> list[SmoothedSample]:
        """Smooth a session into a parallel track.

        Returns an empty list for a session with no fix anywhere: there is no track to
        estimate, and a track of invented positions would be worse than none.
        """
        samples = data.samples
        origin = next((s for s in samples if s.has_position), None)
        if origin is None:
            return []

        frame = LocalFrame(lat0=origin.lat or 0.0, lon0=origin.lon or 0.0)
        filtered = self._forward(samples, frame)
        states, covariances = self._backward(filtered)
        return self._emit(samples, frame, states, covariances)

    # -- the two passes ---------------------------------------------------------------

    def _forward(self, samples: Sequence[Sample], frame: LocalFrame) -> _Filtered:
        """Kalman filter, front to back, updating only where a fix exists."""
        n = len(samples)
        r_base = self.measurement_noise_m**2
        h = np.zeros((2, _STATE))
        h[0, 0] = h[1, 1] = 1.0

        states = np.zeros((n, _STATE))
        covariances = np.zeros((n, _STATE, _STATE))
        predicted_states = np.zeros((n, _STATE))
        predicted_covariances = np.zeros((n, _STATE, _STATE))
        transitions = np.zeros((n, _STATE, _STATE))

        state, covariance = self._initial(samples, frame)
        states[0] = state
        covariances[0] = covariance
        predicted_states[0] = state
        predicted_covariances[0] = covariance
        transitions[0] = np.eye(_STATE)

        last_fix: tuple[float, float, float] | None = None
        if samples[0].has_position:
            last_fix = (samples[0].t, state[0], state[1])

        for k in range(1, n):
            dt = max(samples[k].t - samples[k - 1].t, 1e-6)
            f = _transition(dt)
            state = f @ state
            covariance = f @ covariance @ f.T + _process_noise(dt, self.process_noise)

            transitions[k] = f
            predicted_states[k] = state
            predicted_covariances[k] = covariance

            sample = samples[k]
            if sample.has_position:
                mx, my = frame.to_metres(sample.lat or 0.0, sample.lon or 0.0)
                gated = self._is_outlier(last_fix, sample.t, mx, my)
                r = np.eye(2) * r_base * (self.outlier_variance_factor if gated else 1.0)

                innovation = np.array([mx, my]) - h @ state
                s_matrix = h @ covariance @ h.T + r
                gain = covariance @ h.T @ np.linalg.inv(s_matrix)
                state = state + gain @ innovation
                covariance = covariance - gain @ h @ covariance
                if not gated:
                    last_fix = (sample.t, mx, my)

            states[k] = state
            covariances[k] = covariance

        return _Filtered(
            states=states,
            covariances=covariances,
            predicted_states=predicted_states,
            predicted_covariances=predicted_covariances,
            transitions=transitions,
        )

    def _backward(self, f: _Filtered) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Rauch-Tung-Striebel: sweep back, correcting each second with its own future."""
        states = f.states.copy()
        covariances = f.covariances.copy()

        for k in range(len(states) - 2, -1, -1):
            gain = (
                f.covariances[k]
                @ f.transitions[k + 1].T
                @ np.linalg.inv(f.predicted_covariances[k + 1])
            )
            states[k] = f.states[k] + gain @ (states[k + 1] - f.predicted_states[k + 1])
            covariances[k] = (
                f.covariances[k]
                + gain @ (covariances[k + 1] - f.predicted_covariances[k + 1]) @ gain.T
            )
        return states, covariances

    # -- helpers ----------------------------------------------------------------------

    def _initial(
        self, samples: Sequence[Sample], frame: LocalFrame
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Start on the first fix, admitting how little the first second is known.

        If that fix arrives a minute in, the opening position could be anywhere the surfer
        could have travelled from in a minute, and the covariance says exactly that.
        """
        first = next(s for s in samples if s.has_position)
        x0, y0 = frame.to_metres(first.lat or 0.0, first.lon or 0.0)
        reach_s = abs(first.t - samples[0].t)

        state = np.array([x0, y0, 0.0, 0.0])
        position_var = (self.measurement_noise_m + self.max_speed_ms * reach_s) ** 2
        covariance = np.diag(
            [position_var, position_var, self.max_speed_ms**2, self.max_speed_ms**2]
        )
        return state, covariance

    def _is_outlier(
        self, last_fix: tuple[float, float, float] | None, t: float, mx: float, my: float
    ) -> bool:
        """True when reaching this fix from the last accepted one is physically impossible."""
        if last_fix is None:
            return False
        last_t, last_x, last_y = last_fix
        dt = t - last_t
        if dt <= 0.0:
            return False
        return math.hypot(mx - last_x, my - last_y) / dt > self.max_speed_ms

    def _emit(
        self,
        samples: Sequence[Sample],
        frame: LocalFrame,
        states: NDArray[np.float64],
        covariances: NDArray[np.float64],
    ) -> list[SmoothedSample]:
        """Project back to degrees and attach what we do not know to every second."""
        track: list[SmoothedSample] = []
        for k, sample in enumerate(samples):
            x, y, vx, vy = states[k]
            sigma = math.sqrt(max(0.5 * (covariances[k][0, 0] + covariances[k][1, 1]), 0.0))
            lat, lon = frame.to_degrees(float(x), float(y))
            track.append(
                SmoothedSample(
                    t=sample.t,
                    lat=lat,
                    lon=lon,
                    vx_ms=float(vx),
                    vy_ms=float(vy),
                    position_sigma_m=sigma,
                    confidence=self.confidence_for(sigma),
                    observed=sample.has_position,
                )
            )
        return track

    def confidence_for(self, sigma_m: float) -> float:
        """Map position uncertainty to a 0-1 confidence.

        One knee, no cliffs: 1.0 when the position is pinned, one half at
        ``confidence_sigma_m``, tending to zero as the estimate loosens. Fix availability
        enters through sigma rather than as a separate term -- an unobserved second is
        uncertain *because* its covariance grew, which is the same statement made once.
        """
        return 1.0 / (1.0 + (sigma_m / self.confidence_sigma_m) ** 2)

    # -- payload ----------------------------------------------------------------------

    def encode(self, output: list[SmoothedSample]) -> bytes:
        """Serialise the track. The rows are the whole output, so they are the whole payload.

        The params are written alongside as provenance -- a track on disk should be able to
        say how it was made -- but they are never read back: the output is the rows.
        """
        columns: dict[str, pa.Array] = {
            name: pa.array([getattr(s, name) for s in output], type=pa.float64())
            for name in _COLUMNS
        }
        columns["observed"] = pa.array([s.observed for s in output], type=pa.bool_())
        table = pa.table(columns).replace_schema_metadata(
            {_PARAMS_KEY: json.dumps(self.meta.params, sort_keys=True).encode("utf-8")}
        )
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="zstd")
        return bytes(sink.getvalue().to_pybytes())

    def decode(self, payload: bytes) -> list[SmoothedSample]:
        """Rebuild the track ``encode`` wrote."""
        table = pq.read_table(pa.BufferReader(payload))
        return [SmoothedSample(**row) for row in table.to_pylist()]
