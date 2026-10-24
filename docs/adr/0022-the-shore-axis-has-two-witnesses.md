# ADR-0022: The shore axis has two witnesses, and their agreement is the reliability test

**Status:** accepted · 2026-10-24 · **amends**
[ADR-0011](0011-shore-bearing-from-speed-weighted-velocity.md) rather than superseding it:
its estimator stays, its reliability gate does not

## Context

Phase 6 was planned on the premise that ADR-0011's bearing was wrong. It returned
`coherence 0.365, reliable=False` on the reference session against 0.51° on the synthetic,
and the explanation looked structural: it weights fast seconds and a real session is mostly
slow ones. The plan therefore proposed replacing it with a coastline regression.

**The premise was false, and measuring it first is the only reason we know.** A coast angle
fitted from an independent published geometry lands **4.2° from the bearing ADR-0011 refused
to stand behind.**

| | shoreward | from ADR-0011's bearing |
|---|---|---|
| ADR-0011, speed-weighted velocity, reference session | 71.1° | — |
| GSHHG 2.3.7 full, ±1 km of the peak | 75.3° | **4.2°** |
| OSM via Overpass, ±1 km | 75.5° | 4.4° |
| Natural Earth 1:10m, ±1 km | 64.0° | 7.1° |

So `coherence` was never measuring error. It is the weighted mean resultant length — whether
the per-second votes agree *with each other* — and on a session that is four-fifths paddling
they disagree even when their sum is correct. ADR-0011 reached the right axis and then
declined to publish it, which is a worse failure than being wrong, because nothing downstream
could tell the difference.

Running the whole chain at each angle confirms the axis is not what moves the answer:

```
 shoreward  source                        L3 candidates   L5 waves
     52.0°  OSM, ±200 m window (a bad fit on purpose)  25         12
     64.0°  Natural Earth 1:10m                        26         11
     71.1°  ADR-0011, shipping today                   22         11
     75.3°  GSHHG 2.3.7 full                           21         11
     75.5°  OSM via Overpass                           21         11
     78.7°  OSM, ±1500 m window                        21         11
```

Eleven at every plausible angle. What moves the count is
[ADR-0023](0023-a-wave-must-be-corroborated-by-the-speedometer.md), not this.

## Decision

**Two independent estimators, and `reliable` means they agree.**

1. **The coastline angle** is primary: resample the published geometry at fixed spacing within
   a declared radius of the session's observed centroid, and fit its principal axis.
2. **ADR-0011's speed-weighted bearing** is the second witness, unchanged — same exponent,
   same formula, same code.
3. `reliable` is whether the two land within `max_disagreement_deg`. **`coherence` and the
   Kish effective sample size are still computed and still reported**; they stop deciding.

When only one estimator fires the frame is usable and marked single-witness. When neither
does, L2 returns the unreliable frame it returns today — still not an error and still not a
default bearing.

### Only the angle is used, and the line never renders

This is the decision that makes a coarse source viable, and it is Miguel's: **a line has no
position in this method.** Measured consequences of taking it:

| Source | Licence | Points in 1 km | Spacing | Distance to the sit spot |
|---|---|---|---|---|
| Natural Earth 1:10m | public domain | 1 | 2.7–3.2 km | 549 m, out to sea |
| GSHHG 2.3.7 full | LGPL v3+ | 14 | 96–281 m (median 118) | **15 m, inland** |
| OSM via Overpass | ODbL | 64 | 4–130 m (median 29) | 112 m |

GSHHG puts the spot where Miguel floated for 23 minutes on dry land, and Natural Earth puts
it half a kilometre offshore. **Neither error reaches the arithmetic, because neither line is
drawn and no position is read from it.** Every candidate angle gave the same left/right call
on all ten fast runs of the reference session, including Natural Earth's, 11.3° away.

So the map keeps showing imagery and relief (ADR-0019, ADR-0021) and gains sit-spots, not a
shore line. There is no waterline in the API response, because there is no waterline we can
place.

### The source is GSHHG 2.3.7 full, under LGPL v3+

Chosen because **it agrees with the dense measuring stick to 0.2°** at the window its 118 m
spacing supports. Its LICENSE.TXT permits redistribution with notice and explicitly permits
bundling in software sold for a fee, so a `NOTICE` file satisfies it and nothing is
foreclosed (ADR-0020).

- **OSM via Overpass is the measuring stick and never ships.** ODbL share-alike on a derived
  database is the second reason beyond the reproducibility argument PLAN.md already recorded.
- **Natural Earth is recorded as passing by luck.** It separated correctly on this session and
  it must not be read as validated: with one vertex inside a kilometre, its fit spans several
  kilometres of coast, and its 4.3 m rms residual is a **false confidence signal** — the fit is
  straight because the source is straight. **Residual cannot be the reliability gate**, which
  is the second reason agreement is.

### The window is a declared parameter, because it is the dominant lever

Fitted on OSM, the same anchor gives 142.0° at ±200 m and 168.7° at ±1500 m — a 20.6° swing,
with rms residual growing 14.7 → 123.9 m. A quadratic local-tangent fit does not help
(19.6°). The coast genuinely curves, so the window is a choice and not a fitting artefact.
**Pinned at ±1000 m**, where GSHHG's spacing supports a fit and the sources agree. Anchor
wobble is not a concern at that radius: 40 m of it moves the bearing ≤ 2.56°, and the
observed centroid sits 28 m from the clustered peak for 0.62° of difference.

### The sign comes from the walk, not from the geometry

**No static file can say which way is shoreward here.** GSHHG places the anchor *inside* its
land polygon (ring of 1,160,926 vertices, point-in-polygon true), so the peak-side test and
the land test both fail on the one session we have.

The audit already separates the walk from the session (ADR-0015), and the walk is on land:
across the 60 s before entry and the 430 s after exit, both `baseline` at confidence 0.70,
**all 489 observed walking seconds fall on one side with no exceptions** — median +40 m and
+287 m against a session spanning −140 to +198 m, for 164 m of separation. So:

1. **The walk**, when the audit found one outside the session span.
2. **Ride majority** — net alongshore displacement of the fast runs. The weaker witness: 7 of
   10 and +301 m net on this session.
3. **Neither** — unreliable, and no direction is published.

**L0.6's key therefore travels in L2's params, not its input hash**, which is exactly L6's
pattern in `session.py:metrics_for` and for ADR-0015's reason: the walk decides the sign, but
the audit changes no sample and must not sit in front of the track.

### Peaks are built, and the axis does not depend on them

The plan had a peak-clustering stage in front of the frame, to choose where on the coast to
fit. It is not needed for that: the observed centroid is 28 m from the observed-weighted peak
centroid and changes the angle by 0.62°, against a tolerance of tens of degrees. The
clustering is also not load-bearing in itself — the anchor moves ≤ 24.9 m across 48 parameter
sets, median 9.4 m.

So `PeaksStage` hangs off L1 **beside** L2, the shape of L0.6 beside L1, and exists for the
sit-spots on the map rather than for the frame.

## Consequences

- **ADR-0011's measurements stand and its gate does not.** `min_coherence: 0.85` stops being
  the thing that decides `reliable`. Its own sweep remains the evidence for `speed_exponent:
  4.0`, and a single-witness frame still needs the Kish guard, since the 0.90-coherence /
  1.25-effective-seconds case ADR-0011 found is real and the coastline cannot catch it.
- **The axis is no longer fitted to the data it judges.** L3 finds candidates by projecting
  onto the cross-shore axis; an axis estimated from velocity is therefore partly circular.
  The coastline shares no input with the session at all, which is the methodological reason
  to prefer it as primary even though the two agree.
- **The frame now has an input from outside the recording**, and ADR-0008 is not breached: the
  pipeline consumes no third party's *derived view of this session*. A published coastline is
  reference geography, in the same class as a map projection constant. Written down here
  because it is a judgement, not an obvious call.
- **The extract is committed, and that is a deliberate exception** to the instinct behind
  `.gitignore`. That rule exists for activity files — a GPS trace with timestamps. Agreed with
  Miguel: the spot is not a secret and the geometry is not his. `data/` and `sample_data/`
  stay ignored, and so does `web/verification/`.
- **It lives at `api/src/surf/reference/coast/`, inside the package.** This ADR first said
  `api/data/coast/`, which was wrong twice over and was caught while building PR 6c.
  `.gitignore` carries `data/` with no leading slash, so it matches `api/data/` too and the
  file would never have been committed at all; and `api/Dockerfile` copies only
  `pyproject.toml`, `uv.lock` and `src`, so anything outside `src` is absent from the
  container. Neither failure would have been loud: L2 would have fallen through to its
  velocity fallback and served a single-witness frame. `reference/coast/vendor.py` stays at
  the repo root, because a shapefile reader should not be importable from the package.
  (**`prompts/` has the second half of this bug today** — `llm/audit.py` and
  `llm/adjudicate.py` resolve it from the repo root, which the container does not have. Not
  touched here; it is a separate finding.)
- **The coastline file's sha256 is in L2's params**, so a bearing can never be served under a
  coastline it was not computed from. This is the argument that chose a file over a live
  query: an Overpass-derived bearing moves when a stranger retraces the beach, with no code
  change and no version bump.
- **`CODE_VERSION` bumps and L3–L6 re-key.** The count does not move; it is measured not to.
- **Phase 10 gets a stable axis.** A coastline angle is a property of the beach, so the same
  ride is the same direction in May and in June. A per-session refit could not promise that.
- **Naming the break is still open.** A geometry file holds no beach name; that needs a
  gazetteer, and `app.provenanceNoSpot` stays until one is decided.
