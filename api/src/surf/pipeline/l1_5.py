"""L1.5 -- peaks: where the session sat still, which is where the waves came from.

A surf session is mostly waiting. On the reference recording, **41% of it is spent inside a
20 m circle for over a minute at a time** -- more than the riding and the paddling together.
That is not dead time to be filtered out; it is the one thing in the file that marks the
break itself, and a map of a session that does not show it is missing the subject.

**This stage decides nothing.** It was planned as the front of the shore-axis estimator --
cluster the sitting, regress the coastline near the cluster, take the perpendicular -- and
measurement removed it from that path entirely. Anchoring the coastline fit on the
observed-weighted peak rather than on the session's plain observed centroid moves the fitted
angle **0.62 degrees**, against a tolerance of tens of degrees (ADR-0022). So peaks are not
load-bearing for the frame, and this hangs off L1 **beside** L2 rather than in front of it --
the shape L0.6 already has beside L1, and for the same reason: nothing downstream of the
frame may be invalidated by retuning a clusterer that changes no sample and no axis.

**Three things the measurement changed about the rule.**

*A duration floor is not enough.* The first probe found a cluster lasting 170 s on **10
observed seconds**. A stretch the watch barely saw is not evidence of sitting still; it is
evidence of nothing. So a cluster has to clear a floor on the *fraction* of its span that was
seen, and a fraction separates better than an absolute count: across the reference session the
fraction runs 0.06 to 0.75, median 0.41 against the session's own 0.40, and the thin one is a
clear outlier at 0.06.

*The eleven clusters are one bank, not eleven peaks.* Their centroids sit 4-80 m apart and
collapse to a single area at every merge distance at or above 50 m. The clusters are kept
because a drift between three sit spots is a real and different thing, but the grouping is
computed here rather than left to whatever draws it.

*Spread is not a signal.* The clusterer extends a group while every member stays within the
radius of the running centroid, so the widest member always lands at or near that radius --
measured, spread equalled the radius at *every* radius swept. It is the parameter reflected
back, so it is not reported.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

import pyarrow as pa
import pyarrow.parquet as pq

from surf.geo import LocalFrame
from surf.models import AuditReport, Peak, PeakArea, SessionPeaks, SmoothedSample
from surf.pipeline.stage import StageMeta

NAME = "L1.5"
"""Peaks are stage L1.5: off to the side of the chain, not a step along it."""

CODE_VERSION = "1"
"""Bump when a peak changes meaning, so cached rows are not reused under a new definition."""

_COLUMNS = ("lat", "lon", "t_start", "t_end", "observed_s", "area")
_AREAS_KEY = b"surf.l1_5.areas"
"""Parquet metadata entry holding the merged areas -- part of the output, not provenance."""


class PayloadError(RuntimeError):
    """A cached payload is not something this stage wrote."""


@dataclass(frozen=True)
class PeaksInput:
    """What L1.5 needs: the smoothed track, and the audit that bounds the session.

    ``audit`` is optional, and when it is absent the whole recording is clustered. That is
    usually wrong rather than merely weaker -- a surf file routinely opens on the walk down
    and closes on the walk back, and standing still on the sand for eight minutes is the most
    convincing peak in the file. The caller gets what it asked for and the key records which
    it was.
    """

    track: Sequence[SmoothedSample]
    audit: AuditReport | None = None


@dataclass(frozen=True)
class PeaksStage:
    """L1.5: cluster the seconds the session held still, and group them into places."""

    radius_m: float = 20.0
    """How far a member may sit from its cluster's running centroid.

    Swept rather than assumed, because the first probe suspected it was doing the work. It is
    not: across 48 parameter sets the observed-weighted area centroid moved at most 24.9 m,
    median 9.4 m. A board on a swell moves several metres without the surfer going anywhere,
    so the radius is a statement about what sitting still looks like at 1 Hz GPS.
    """
    min_duration_s: float = 60.0
    """Shortest sit counted. Under a minute is a pause between paddle strokes."""
    min_observed_fraction: float = 0.25
    """Least of its own span a cluster must have been seen for.

    The measured finding, and the one caveat the first probe raised that this rule had to
    answer. Set well below the session's own coverage (0.40) so an ordinarily blind sit still
    counts, and well above the 0.06 of the cluster that was 170 s of almost nothing.
    """
    merge_m: float = 50.0
    """Centroids closer than this are the same place. Measured: the reference session's
    eleven clusters collapse to one area at every value at or above 50 m."""
    audit_key: str = ""
    """L0.6's cache key, carried as a **param** rather than in the input hash (ADR-0015).

    A peak sited in the walk up the beach is not a peak, so a different audit is a different
    set of peaks and has to re-key. But the audit changes no sample, so it must not sit in
    front of L1. Empty when no audit was supplied, which the key then records."""

    @property
    def meta(self) -> StageMeta:
        """Stage identity. Every param moves the peaks, so every one is in the key."""
        return StageMeta(
            name=NAME,
            code_version=CODE_VERSION,
            params={
                "radius_m": self.radius_m,
                "min_duration_s": self.min_duration_s,
                "min_observed_fraction": self.min_observed_fraction,
                "merge_m": self.merge_m,
                "audit_key": self.audit_key,
            },
        )

    def run(self, data: PeaksInput | Sequence[SmoothedSample]) -> SessionPeaks:
        """Find the sits, drop the ones the watch barely saw, and group what is left."""
        payload = data if isinstance(data, PeaksInput) else PeaksInput(track=data)
        audit = payload.audit
        observed = [
            s
            for s in payload.track
            if s.observed and (audit is None or audit.surfing_t_start <= s.t <= audit.surfing_t_end)
        ]
        if not observed:
            return SessionPeaks()

        local = LocalFrame(lat0=observed[0].lat, lon0=observed[0].lon)
        points = [(s.t, *local.to_metres(s.lat, s.lon)) for s in observed]
        kept = [cluster for cluster in self._cluster(points) if self._worth_keeping(cluster)]
        if not kept:
            return SessionPeaks()

        groups = self._merge(kept)
        peaks: list[Peak] = []
        areas: list[PeakArea] = []
        for index, group in enumerate(groups):
            weight = sum(len(cluster) for cluster in group)
            centre_x = sum(x for cluster in group for _, x, _ in cluster) / weight
            centre_y = sum(y for cluster in group for _, _, y in cluster) / weight
            area_lat, area_lon = local.to_degrees(centre_x, centre_y)
            areas.append(
                PeakArea(
                    lat=area_lat,
                    lon=area_lon,
                    peaks=len(group),
                    observed_s=weight,
                    held_s=sum(c[-1][0] - c[0][0] for c in group),
                )
            )
            for cluster in group:
                lat, lon = local.to_degrees(*self._centroid(cluster))
                peaks.append(
                    Peak(
                        lat=lat,
                        lon=lon,
                        t_start=cluster[0][0],
                        t_end=cluster[-1][0],
                        observed_s=len(cluster),
                        area=index,
                    )
                )

        peaks.sort(key=lambda peak: peak.t_start)
        return SessionPeaks(peaks=peaks, areas=areas)

    def _cluster(
        self, points: Sequence[tuple[float, float, float]]
    ) -> list[list[tuple[float, float, float]]]:
        """Greedy: a cluster extends while **every** member stays within the radius.

        Every member, not just the newest, and not just the centroid -- which is what makes a
        cluster a place rather than a slow drift along the beach. The consequence is that the
        widest member ends up at the radius by construction, which is why ``spread`` is not
        reported as if it had been measured.
        """
        clusters: list[list[tuple[float, float, float]]] = []
        current: list[tuple[float, float, float]] = []
        centre_x = centre_y = 0.0
        for point in points:
            _, x, y = point
            if not current:
                current, centre_x, centre_y = [point], x, y
                continue
            n = len(current)
            next_x, next_y = (centre_x * n + x) / (n + 1), (centre_y * n + y) / (n + 1)
            members = [*current, point]
            if all(
                ((px - next_x) ** 2 + (py - next_y) ** 2) <= self.radius_m**2
                for _, px, py in members
            ):
                current = members
                centre_x, centre_y = next_x, next_y
            else:
                clusters.append(current)
                current, centre_x, centre_y = [point], x, y
        if current:
            clusters.append(current)
        return clusters

    def _worth_keeping(self, cluster: Sequence[tuple[float, float, float]]) -> bool:
        """Long enough, and seen enough of the time to mean anything."""
        span = cluster[-1][0] - cluster[0][0]
        if span < self.min_duration_s:
            return False
        return len(cluster) / span >= self.min_observed_fraction

    @staticmethod
    def _centroid(cluster: Sequence[tuple[float, float, float]]) -> tuple[float, float]:
        n = len(cluster)
        return sum(x for _, x, _ in cluster) / n, sum(y for _, _, y in cluster) / n

    def _merge(
        self, clusters: Sequence[Sequence[tuple[float, float, float]]]
    ) -> list[list[Sequence[tuple[float, float, float]]]]:
        """Group clusters whose centroids are within ``merge_m`` of one another.

        Single-link, so three sit spots strung 40 m apart along a bank come out as one area
        even though the ends are 80 m apart. That is the right answer for a sandbank and it is
        what the measurement found: the reference session's centroids run 4-80 m apart and are
        one place.
        """
        centres = [self._centroid(cluster) for cluster in clusters]
        parent = list(range(len(clusters)))

        def root(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                dx = centres[i][0] - centres[j][0]
                dy = centres[i][1] - centres[j][1]
                if dx * dx + dy * dy <= self.merge_m**2:
                    parent[root(i)] = root(j)

        grouped: dict[int, list[Sequence[tuple[float, float, float]]]] = {}
        for index, cluster in enumerate(clusters):
            grouped.setdefault(root(index), []).append(cluster)
        return [grouped[key] for key in sorted(grouped)]

    def encode(self, output: SessionPeaks) -> bytes:
        """Serialise the peaks: rows as columns, the merged areas as file metadata.

        The areas are part of the output rather than provenance, so they travel in the
        payload the way L2's frame does -- a cache hit has to return everything a run would.
        """
        columns: dict[str, pa.Array] = {
            name: pa.array(
                [getattr(peak, name) for peak in output.peaks],
                type=pa.int64() if name in {"observed_s", "area"} else pa.float64(),
            )
            for name in _COLUMNS
        }
        table = pa.table(columns).replace_schema_metadata(
            {_AREAS_KEY: json.dumps([area.model_dump() for area in output.areas]).encode()}
        )
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="zstd")
        return bytes(sink.getvalue().to_pybytes())

    def decode(self, payload: bytes) -> SessionPeaks:
        """Rebuild the peaks ``encode`` wrote."""
        table = pq.read_table(pa.BufferReader(payload))
        raw = (table.schema.metadata or {}).get(_AREAS_KEY)
        if raw is None:
            msg = f"{NAME} payload carries no area metadata: it was not written by this stage"
            raise PayloadError(msg)
        return SessionPeaks(
            peaks=[Peak(**row) for row in table.to_pylist()],
            areas=[PeakArea(**row) for row in json.loads(raw)],
        )
