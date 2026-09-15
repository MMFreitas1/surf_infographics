# Design brief — surf session drill-down

**For:** iterating the UI in Claude Design, then handing the result back for build.
**Status:** brief only. No screen here is built yet. Data model and available numbers are real.
**Companion:** [`PLAN.md`](./PLAN.md) phases 5–11 · [`docs/adr/`](./docs/adr/) for why things are the way they are.

---

## 1. What this is

A local-first app that turns one Garmin surf recording into something a surfer can read, and a
series of them into an answer to *am I getting better?*

It is a **three-level drill-down**:

```
SESSIONS  ─── am I improving? ──────────  % change · surf level · trends · 3D correlation
   │
   └─ SESSION  ─── how was that surf? ───  wave count · sea state · aerobic · distance
         │
         └─ WAVE  ─── how was that ride? ─  duration · direction · speeds · manoeuvres
```

Every level ends with a short LLM comment in prose, and offers a correlation plot the user drives.

---

## 2. Non-negotiable design constraints

These come from the project's honesty rules. A design that breaks one is wrong, however good it looks.

1. **Half the data does not exist.** On the reference session the watch had a GPS fix for
   **48.8%** of the time — the wrist is underwater. Every screen has to be legible with half its
   input missing. This is a property of the sport, not a bug we will fix later.
2. **Three states, always distinguishable: measured · estimated · blind.** A second the watch
   recorded and a second the smoother invented must never look the same. Currently: solid /
   dashed / hatched. Improve the visual language, keep the distinction absolute.
3. **Nothing here is validated.** No wave count, speed or level is a measured fact — they are
   readings of the data (ADR-0013). The word *proposed* or an equivalent must be visible without
   hunting. Design the honest version, not a confident dashboard.
4. **Every number carries its coverage.** A metric from a wave the watch barely saw must look
   weaker than one it saw fully. Coverage is a first-class visual property, not a tooltip.
5. **It must work offline.** Basemaps, sea state and the LLM can all be absent. Every panel needs
   a designed unavailable state — not a spinner that never resolves.
6. **A missing number is shown as missing.** Never zero, never a dash that reads as zero.

---

## 3. Units and formats

| | |
|---|---|
| Speed | **km/h** everywhere in the UI. (SI stays inside the pipeline; conversion happens at the edge) |
| Distance | metres under 1 km, then km to one decimal |
| Duration | `m:ss` for session time, `12.4s` for a ride |
| Time of day | local to the session |
| Temperature | °C |
| Swell height | metres, one decimal · period in seconds · direction in degrees plus compass point |
| Energy | kJ/m |
| Heart rate | bpm |
| Coverage | whole percent |

Realistic surfing speeds are **25–35 km/h**. Anything above 40 is almost certainly noise —
design should make an outlier look suspicious rather than impressive.

---

## 4. Level 1 — Sessions

The tab a returning user lands on. Session list in the Garmin idiom, **below** the infographics.

**Its entire purpose is progression.** Each metric, card and infographic carries a **% change
against the previous session in its top-right corner**.

- Surf level badge — **Beginner · Intermediate · Intermediate-high · Advanced · Athlete**.
  First assessed after 5 sessions, revisited every 10. It is a claim about a person: the design
  must make its reasoning reachable, never a bare label.
- Trend charts per metric over time
- **3D correlation plot** — user picks two metrics against time, and can rotate/manipulate it
- LLM prose: *is the improvement real, and in what*
- Session list: date, spot, duration, wave count, and the change chips

Needs a designed empty state — **before 5 sessions there is no level**, and that is normal, not an error.

---

## 5. Level 2 — Session

The main screen. Everything below is one session.

### The GPS graph — the centrepiece

- The track, with every proposed wave marked
- **Selecting a wave hides the others** and highlights it alone
- **Play button: 250 ms per step**, metrics ticking as it advances, interpolated between seconds
- Measured / estimated / blind visible throughout
- **Radial overlay**: swell 1 and swell 2 cones plus a wind cone. Cones labelled with wave height
  and wind km/h. Swell colours **opposed**; colour strength carries period. **Legend bottom-right**
- Shore line drawn once direction is trustworthy (Phase 6)

### Sea state

Cards for **swell 1 → 4** where the provider has them — **card size proportional to wave height**,
so the hierarchy is readable before any number is. Plus wind speed and direction, sea temperature,
time of day, and combined swell energy.

Design for **fewer than four swells**: the free data source often returns two or three. Padding
with empty cards would be a lie about the sea.

### The rest of the session screen

- **Wave count — spotlighted, the biggest element on the dashboard**
- Waves per 10 minutes, with rate
- Distance covered, split **swimming vs riding** — and honest that only measured seconds count
- **Aerobic**: avg BPM · max BPM · zones · effort vs reward · fatigue, read from HR against
  recovery time and paddling speed
- **Device confidence**: coverage, number of blind windows, and how many fixes the cleaner rejected
- **State ribbon**: riding / paddling / waiting / blind as one bar across the session
- **Wave-shape small multiples**: each ride's speed profile, normalised, side by side
- **Speed distribution**: histogram, so an artefact looks like an artefact
- **Rhythm**: ride/rest intervals
- Correlation plot, two metrics of the user's choosing
- LLM prose: *how that surf went, addressed to the athlete*

Heart rate is the **only signal with no gaps** — 100% coverage against 48.8% for position. The
aerobic block is the one place the design can be fully confident, and that contrast is worth using.

---

## 6. Level 3 — Wave

Reached by selecting a wave on the GPS graph, or from a dropdown.

| Metric | Note for design |
|---|---|
| Duration | |
| **Direction** — left / right / straight | carries a confidence; can be undeterminable |
| Number of manoeuvres | coarse at 1 Hz. A change followed by no speed is a **fall**, not a manoeuvre — worth showing |
| Take-off speed | reads against wave speed to judge paddling |
| Approximate wave speed | needs sea-state data; may be absent |
| Top speed · average speed | km/h |
| Bottom turn profile | **still being researched** — design a placeholder, do not invent the visual |
| Path straightness ratio | the rail-to-rail proxy |
| Avg BPM · max BPM | |
| Correlation plot | two metrics of the user's choosing |
| LLM prose | *what the straightness and manoeuvres imply about technique* |

Every one of these needs a visible coverage qualifier. A wave the watch saw 12% of produces
numbers that are mostly the smoother's opinion.

---

## 7. Shared components

- **% change chip** — top-right of a metric. Needs up / down / flat / no-comparison states
- **Coverage badge** — how much of this was measured. Appears on waves, sessions, and any derived number
- **LLM prose block** — ~100 tokens of plain prose, no lists. Needs a generating state, an
  offline/unavailable state, and a clear "this is a model's reading" signal
- **Correlation plot** — two user-chosen metrics; 2D at Session and Wave level, 3D over time at Sessions level
- **Unavailable state** — one consistent treatment for offline, no key, no data

---

## 8. Real numbers, so mockups are honest

From the actual reference recording, measured 2026-08-31:

| | |
|---|---|
| Session length | 63.2 min · 3,790 samples at 1 Hz |
| Position coverage | **48.8%** · 128 blind windows · 32.4 min blind · longest gap 107 s |
| Heart rate | 66–139 bpm, mean 102 · **100% coverage** |
| Distance | 3,713 m — measured seconds only; it does not advance while blind |
| Proposed waves | **22** before cleaning and scoring · 2 of them from *entirely* estimated seconds, 8 more under 25% coverage |
| Raw top speed | 74.8 km/h — **noise**. 24 fixes over 40 km/h |
| Device temperature | 21–23 °C — case temperature, not sea temperature |
| Shore direction | currently **undeterminable** on this session (coherence 0.37); Phase 6 addresses it |

A realistic mockup shows roughly 12–22 waves, top speeds in the high 20s km/h, and a lot of
qualified numbers.

---

## 9. Do not design these

Not because they are hard — because the data cannot support them, and a beautiful panel is the
most persuasive way to ship a lie:

- **Wave face height** — not derivable from a wrist GPS trace
- **Turn-by-turn manoeuvre breakdown** — 1 Hz, half of it estimated. A count with a confidence is the ceiling
- **Sea temperature from the device** — that is case temperature. Real sea temp comes from the marine API
- **Accuracy, precision or recall figures** — nothing is validated (ADR-0013)
- **A total distance that includes blind time** — the watch stops counting; so do we

---

## 10. Open questions for the design pass

1. How do measured / estimated / blind read at a glance without the chart becoming noise? The
   current hatch had to be lightened twice — a session has **128 separate blind windows**, so
   blindness is shredded, not blocky.
2. How does a wave with 12% coverage look different from one with 100%, at card size?
3. Where does the % change chip live so it informs without dominating?
4. What does the wave count spotlight look like when the count is a *proposal*?
5. How do the swell cones overlay a map without burying the track?
6. Mobile: is this a desktop-first tool, or does it need to work on a phone in a car park?

---

## 11. Handover back

When the design settles, what I need to build it:

- Screen layouts per level, with the empty / offline / low-coverage states drawn
- The visual language for measured · estimated · blind, and for coverage
- Colour tokens and type scale, light and dark
- Interaction notes for wave selection, the 250 ms playback, and the correlation plots
- Anything you changed your mind about, so `PLAN.md` and the ADRs can follow
