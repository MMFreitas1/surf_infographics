# Handoff: Surf Analytics — v1.0

**Product:** Surf Analytics (MF Concepts · Technology)
**Design system:** MF Concepts Design System
**Language of the UI:** Portuguese (pt-PT)
**Fidelity:** **High-fidelity (hifi)** — final colors, type, spacing, charts and interactions.
**Data source repo:** `MMFreitas1/surf_infographics` (see `source-repo.md`)

---

## Overview

A local-first desktop analytics tool for a surf session logger. A GPS/HR watch records a
surf session as a 1 Hz FIT file; roughly **half the samples are missing** (the watch loses
fix while the surfer is in the water). The entire design exists to answer one question
honestly: *what do we actually know, and what are we guessing?*

The tool is a **three-level drill-down**, one screen per level, selected by a tab bar:

| Level | Tab | Question it answers |
|---|---|---|
| N1 | **Sessões** | "Am I improving?" — cross-session stats, level, bivariate + comparative analysis, session list |
| N2 | **Sessão** | "How was this surf?" — animated track map, distance/cadence/speed/return charts, sea state, aerobic panel, wave thumbnails |
| N3 | **Onda** | "How was this wave?" — GPS wave profile with animated crest, per-wave metrics, direction, manoeuvres, coach reading |

Two cross-cutting ideas the developer **must** preserve, because the whole design rests on them:

1. **Measured / estimated / blind language.** Solid stroke = GPS-measured. Dashed
   translucent stroke (`#3E6B7C`) = estimated/interpolated. Absence + a dedicated "blind
   rail" = no data at all. Never a hatch, never a fake value.
2. **Coverage expressed typographically.** A number derived from low-coverage data is
   rendered *lighter and more transparent* than a fully-measured one, plus a small
   coverage arc. See `numCss()` below.

An LLM ("AI Surf Coach", `llama-3.1-8b-instruct`, local) writes three prose readings —
*Nível de Surf*, *Qualidade da Sessão*, *Técnica de Onda*. Every LLM output is signed with
the model line and is **never** presented as measurement.

---

## About the design files

The files in `prototype/` are **design references created in HTML** — a working prototype
that shows the intended look, motion and behavior. They are **not production code to copy
directly**.

The task is to **recreate these designs in the target codebase's existing environment**
(the source repo is a Next.js + TypeScript app: `web/src/app/...`, Tailwind-ish
`globals.css` custom properties) using its established patterns, component library and
data layer. Where no equivalent exists yet, pick the most appropriate approach for that
codebase and implement the design there.

The prototype's data is **synthetic but statistically shaped** to match the real findings
in `docs/data-findings.md` (≈48.8% coverage, ≈127 blind windows, 1 Hz, ~3790 samples,
~63 min session). Replace it with the real `ActivitySummary` / `WaveCandidate` records.

### Running the prototype
Open `prototype/Surf Analytics.dc.html` in a browser (served over http — it loads sibling
files). The basemap tiles come from `tile.openstreetmap.org`; if the probe tile fails the
map falls back to a warm grid, which is a designed state, not a bug.

---

## Screens / Views

Global frame for all three levels:

- Outer container `min-width: 1440px`, inner `max-width: 1500px`, `margin: 0 auto`,
  `padding: 0 46px 90px`. Page background `--warm-50` `#FBF7F0`. This is a **desktop
  tool** — it is intentionally not responsive below 1440px.
- **Masthead:** `logo-mark.png` at 34×34, then mono eyebrow `MF CONCEPTS · TECHNOLOGY`
  (10.5px, `.22em`, uppercase, `--text-muted`). `<h1>` "Surf Analytics" — Saira 52px/600,
  `letter-spacing: -.035em`, `line-height: .94`, `--ink-800`. Right side: mono 10px
  `.14em` `Local-first · FIT · {spot}` in `--text-subtle`.
- A **2px `--gradient-brand` rule** under the masthead (`margin: 22px 0 0`). This is the
  only gradient bar in the product — do not repeat it.
- **Tab bar:** flex, `gap: 4px`, `border-bottom: 1px solid --border`. Each tab is Saira
  16px/600. Active tab: `--warm-100` background, `--ink-800` text, 2px `--amber-500` under-
  line. Inactive: transparent, `--text-muted`. Transition `background/color --dur-fast --ease-out`.
- **Dismissible method banner** (`banner` state, shown once): `--gradient-ink` card,
  `--radius-lg`, `--shadow-sm`, `padding: 26px 30px`, a 3px `--gradient-brand` strip on the
  left edge, grid `1fr auto`. Amber eyebrow "Como estes números são feitos"; body 15px/1.7
  `--warm-50` with `--amber-300` inline emphasis on the three LLM-inferred artifacts;
  primary Button "Compreendi" dismisses.
- **Section headers** (used ~6×): 7×7px `--amber-500` square + mono 11px `.24em` uppercase
  `--ink-800` label + `flex: 1` 1px `--border` rule. `padding: 40px 0 18px`.
- **Footer:** 1px `--border` top, mono 10px `.12em` uppercase `--text-subtle`:
  `Sessão em {spot} · {samples} amostras a 1 Hz`.
- **Entrance motion:** every level section animates `mf-fade-up --dur-slow --ease-out both`
  (opacity 0→1, `translateY(10px)`→0). Charts additionally grow once per level visit via an
  `anim` 0→1 cubic ease-out over 900ms (32ms `setInterval`, **not** rAF — see note below).

### N1 · Sessões (`data-screen-label="N1 Sessoes"`)

**Purpose:** see progression across 10 sessions / 6 weeks.

1. **Stat tiles** — `grid-template-columns: repeat(5, 1fr)`, `gap: 14px`. Each tile is a
   button: `--surface`, 1px `--border`, `--radius-lg`, `--shadow-sm`. Contains a mono 9.5px
   `.15em` uppercase label (left) + delta chip (right), then the value on a fixed 48px row
   (Saira, ~30–34px/600, weight+opacity from coverage) with a mono 12px unit.
   *Hover:* `translateY(-5px)`, `box-shadow: 0 14px 26px -12px rgba(18,40,50,.34)`,
   `border-color: --amber-400`.
   *Delta chip:* mono 9.5px, `--radius-full`, `2px 7px`; up = `--success-soft`/`--success`,
   down = `--danger-soft`/`--danger`, flat = `--surface-2`/`--text-muted`, prefixed `▲ +`,
   `▼ `, `— `. Tiles: **Total de Ondas** (solid bar, amber for the current session — no
   "propostas por confirmar" split), **Duração**, **Cobertura GPS**, **Velocidade máxima**,
   **Onda mais longa**.
   Clicking a tile opens the breakdown panel below it.
2. **Breakdown panel** (`bdOpen`) — `--surface` card with a **2px `--amber-500` top border**
   and 1px `--border` on the other three sides, `--radius-lg`, `padding: 24px 28px 18px`.
   Header: amber mono eyebrow "Detalhe", Saira 23px/600 title, 12px `--text-muted` sub;
   right side three controls — an order toggle (tempo ⇄ spot), "ajustar linha de regressão",
   and a 30×30 `×` close button. Body is a `viewBox="0 0 1360 330"` SVG that cross-fades
   (`.g { transition: transform .55s cubic-bezier(.22,1,.36,1), opacity .4s linear }`)
   between a **time series** (bars + range whiskers + per-wave dots + optional dashed
   `--amber-600` regression line) and a **per-spot box plot** (`--blue-500` @ 20% box,
   `--blue-600` 1.4px stroke, `--amber-500` 2.6px median). Mono 9.5px legend below a 1px rule.
3. **Nível de surf** — `--gradient-ink` card, `grid-template-columns: 400px 1fr`.
   Left: mono eyebrow "Próxima avaliação em 5 sessões", the level name in Saira 40px/600
   (`letter-spacing: -.03em`) colored per level, and a 5-step progress strip (3px gaps)
   labelled "Iniciado"→"Atleta". Right: the LLM `prose.sessions` at 15px/1.75 `--warm-50`,
   with the model signature in mono 10px `#5E7178` above a `rgba(251,247,240,.14)` rule.
   **Empty state** (`poucasSessoes` prop / <3 sessions): dashed `--border-strong` card on
   `--warm-100`, "São necessárias 3 sessões. Tens N." + a Saira 64px `--warm-300` `N/3`.
   Copy explicitly says this is normal, not an error.
4. **Análise bivariada** — `--surface` card. Two `<select>`s (X in `--blue-700` label,
   Y in `--amber-700`) over a shared metric list; `viewBox="0 0 1160 470"` scatter: 1.4px
   `--ink-800` axes at x=82 / y=392, dashed `--amber-600` least-squares fit, one circle per
   session — **radius = GPS coverage**, `--blue-500` for past sessions, `--amber-500` for
   the current one. Legend row carries the r value in `--amber-700`.
5. **Análise comparativa** — `--surface` card, `viewBox="0 0 1160 400"`. Two `<select>`s
   (A = `--blue-500` swatch, B = `--amber-500`) + a row of metric chips. Renders bars, box
   plots, areas and lines depending on the metric, with invisible hover zones driving an
   overlay group (`cmp.ovLines` / `ovDots` / `ovText`). Baseline 1.2px `--ink-800` at y=330.
6. **Sessões list** — `border-top: 1.5px solid --ink-800`, then rows on
   `grid-template-columns: 110px 1fr 92px 84px 100px 96px 150px 100px`, `gap: 14px`,
   `padding: 11px 6px`, 1px `--border` between, `hover: --warm-100`, whole row clickable.
   Columns: date (mono 12px), spot + tag chip, duration, waves, **coverage donut**
   (14×14 SVG, `--warm-300` track + `--blue-600` arc, `rotate(-90 11 11)`) + `%`,
   longest wave, a 140×20 sparkline of per-wave bars, delta chip.

### N2 · Sessão (`data-screen-label="N2 Sessao"`)

**Purpose:** understand one session.

- **Hero count:** `stats.realWaves` in Saira **104px**/600, `line-height: .84`,
  `letter-spacing: -.045em`, `--blue-600`, between a 1.5px `--ink-800` top rule and a 1px
  `--border` bottom rule. Waves vs. non-waves are separated in the data pipeline — the UI
  shows one number, not a proposal split.
- **Body grid:** `1fr 440px`, `gap: 26px`, `align-items: start`.
- **Track map card** (left, top): header with the spot as a mono eyebrow and two controls
  — "Sobreposição radial" toggle and a 40×34 play/pause button (`--accent` fill,
  hover `--accent-hover`). Map body is `height: 470px` on `--warm-100`, `overflow: hidden`:
  - OSM raster tiles at z17 around 37.9107, −8.8360, probed with one real `Image()` on
    mount; a `--warm-50` @36% `mix-blend-mode: screen` veil warms them into the palette.
    Failure state = a 44px `--warm-200` repeating-linear-gradient grid.
  - SVG overlay: swell cones + radials + rings + spokes (`--ink-600`, opacity .07–.3),
    estimated track (`#3E6B7C`, 2px, `4 4` dash, .32), measured track (`--blue-600`, 2.4px),
    per-wave marks and dots (clickable), and a 6px playhead dot with a 2px `--warm-0` ring.
  - **Legend** bottom-right: `rgba(251,247,240,.95)`, 1px `--border`, `--radius-md`,
    `--shadow-sm`, mono 9–10px rows.
  - **Selection callout** top-left when a wave is picked: `--gradient-ink`, `--radius-md`,
    `--shadow-lg`; amber mono "Isolada · restantes ocultas", Saira 17px title, mono 10.5px
    meta, then "Abrir onda" (`--primary` on `--ink-900` text) and "Ver todas" (ghost,
    `--blue-300`).
  - Below the map: clock (mono 12px, min-width 52px) + `range` scrubber (0–3789, 250 ms per
    step) + mono 10px "250 ms / passo"; a 4-up live tick readout between two 1px rules; and
    the **fita de estados** — a 20px state ribbon (`--warm-100` base, `--radius-sm`) with a
    playhead, plus a separate **9px blind rail** underneath for unobserved spans, and a
    mono 9.5px key.
- **Four small chart cards** in a `1fr 1fr` grid of two stacked columns, all
  `--surface` / 1px `--border` / `--radius-lg` / `--shadow-sm` / `padding: 20px 22px`,
  each titled with a mono 10px `.2em` uppercase `--ink-800` eyebrow:
  - **Distância** — Saira 46px value + km, an 11px two-part split bar (swim vs ride),
    and a `1fr 1fr` readout.
  - **Cadência** — `0 0 400 168` area+line (`--blue-500` @14% fill, `--blue-600` 2px line,
    3px dots), baseline at y=132.
  - **Velocidade** — a bell curve (`--blue-500` @16%), `--amber-500` 2px mean line,
    two dashed `--ink-500` @45% ±1σ lines, baseline at y=118.
  - **Retorno** — `--warm-400` @55% bars behind an `--amber-600` 2px line with 3px dots.
- **Perfis de onda** — a `repeat(5, 1fr)` grid of 132px tall **flip cards**
  (`perspective: 900px`; hover `transform: rotateY(360deg)`). Front: wave number, a
  coverage badge, a 60×30 mini track (dashed estimated + solid `--blue-600` measured +
  a 2px `--amber-500` start dot), then avg km/h and duration in Saira 16px/600 with mono
  8px units. A lock toggle in the card header reveals a 22×22 `--danger` delete button at
  the top-right of each thumbnail (`--radius-full`, hover fills `--danger`).
- **Right column:**
  - **Estado do mar** — `--surface` card. Swell cards sized by swell height (card height *is*
    the datum); **no card is drawn for a swell the provider didn't report** — that absence is
    the design. `API marinha · 3 de 4` in mono 9.5px. Below: a `1fr 1fr` fact grid.
  - **Aeróbico** — `--gradient-ink` card. `--blue-300` eyebrow + a blue `Badge`
    "100% COBERTURA"; the copy explicitly names this as the only gap-free signal. Three
    Saira 28px stats, a 400×90 HR trace (`--blue-400` 1.4px line, @13% area), five zone
    bars (4px, `rgba(251,247,240,.12)` track), and a two-up effort readout.
  - **Qualidade da sessão** — `--surface` card with a **3px `--accent` left border**; 6px
    `--accent` dot + `--accent-hover` mono eyebrow; `prose.session` at 14px/1.78; model
    signature below a 1px rule. This border+dot treatment marks *every* LLM panel.

### N3 · Onda (`data-screen-label="N3 Onda"`)

**Purpose:** inspect a single wave.

- **Header:** 1.5px `--ink-800` top / 1px `--border` bottom, `padding: 26px 0`.
  "Onda {n}" in Saira 40px/600 `-.035em`, mono 12.5px `{time} · {duration}`, and a
  `<select>` to jump between waves.
- **Grid:** `1fr 420px`, `gap: 26px`.

#### Perfil da onda — the centerpiece

`--surface` card, `padding: 22px 24px`. Header: mono eyebrow "Perfil da onda" + a
transport group (mono 11px `{clock} / {total}`, a 190px `range` with `step="0.1"`, and a
40×34 `--accent` play button).

SVG `viewBox="0 0 720 300"`. **This is a GPS map of the wave, not a time graph:**

- **Horizontal axis = distance perpendicular to shore**, land to the **right**.
  **Vertical axis = metres along the shore.** Plot box `PX0=64, PX1=646, PY0=34, PY1=246`.
  Scale: `min((PX1-PX0)/max(8,(xHi-xLo)*1.1), (PY1-PY0)/max(8,(yHi-yLo)*1.6))`, centered.
  ⚠️ **Open decision carried into v1.0:** this is a *fitted* scale, so along-shore and
  shoreward metres are not guaranteed 1:1. Locking a true 1:1 aspect is a deliberate
  follow-up, not an oversight — decide it before shipping.
- **Coastline, inferred from the GPS data:** a dashed `--amber-500` @50% line 1.6px
  `7 5` from (672,16) to (700,266) — a ~6.6° tilt — plus a land band
  `polygon 672,16 712,16 712,266 700,266` filled with `#wp-shore`
  (`--amber-400` 0% → 34%, left→right).
- **Wave crest** — a **136px wide** `<rect>` from y=16, height 250, filled with the
  `#wp-crest` horizontal gradient and clipped by `#wp-mask` (a vertical white fade so the
  crest dissolves top and bottom). The whole crest group is `rotate(-6.6°)` about the crest
  line, so it stays parallel to the coast, and **sweeps left→right as time advances** —
  that sweep *is* the clock. Stops: `--blue-700` 0 → `--blue-700` .22 @26% (dorso, ocean
  side) → `--blue-600` .48 @48% → `#8ED2F2` .82 @60% → **`#FFFFFF` .95 @66.5% (the foam
  lip)** → `--blue-400` .5 @72% → `--blue-300` .16 @88% → 0 (the face fading toward shore).
  Over it: a 3.2px `#FFFFFF` @90% crest line and a 1.2px `--blue-600` @40% lip line.
- **Track:** dashed `#3E6B7C` @45% for estimated spans, 2.4px `--ink-800` @24% for measured
  spans (the full path, as context), and a 3px `--amber-500` **trail** drawn only up to the
  current time.
- **Surfer:** a 13px `--amber-500` @18% halo + a 6.5px `--amber-500` dot with a 1.8px
  `--warm-0` ring, sitting on the wave face **8px ahead of the crest line**. A live speed
  readout in `--amber-700` 12px sits 22px above it, with a 4px `--warm-50` paint-order
  stroke so it stays legible over the crest.
- **Manoeuvres:** 4px `--amber-600` dots at local speed minima, labelled "manobra" in 9px.
- **Axis legends only — no grid, no numeric axis labels.** Three mono 9px labels:
  `PERPENDICULAR À COSTA — SENTIDO DA ONDA →` at (64,288),
  `LINHA DE COSTA INFERIDA DO GPS` rotated −90° at (700,260) in `--amber-700`,
  `AO LONGO DA COSTA` rotated −90° at (22,246).
- **Legend strip** under the SVG: four mono 9.5px items with gradient/dot/dash swatches.
- **Motion:** an 80 ms tick advances `wNow` by 0.08 s, and both crest and surfer positions
  are **Catmull–Rom interpolated** between 1 Hz samples (`crAt(t)` for the point, `crPath()`
  for the path) so nothing snaps from sample to sample.
- The **"queda" (fall) concept was removed entirely** — a fall means the wave ended, so it
  is not a separate state.

#### Rest of N3

- **Metric cards:** `repeat(3, 1fr)`, `gap: 18px`. Each card has a **2px top border colored
  by coverage** (`--blue-500` ≥.6, `--amber-400` ≥.25, else `--warm-300`), a 14×14 coverage
  arc, and the value in Saira ~30px with coverage-driven weight/opacity. Six metrics:
  Duração (s), Velocidade máxima, Velocidade média, Vel. de take-off (km/h),
  Distância percorrida (m/km), BPM (méd/máx).
- **Perfil do bottom turn — reservado:** a deliberately empty, dashed, sized placeholder
  (`VISUAL NÃO DESENHADO / investigação aberta — nada inventado aqui`). **Keep it.** It is
  the honesty rule made visible; do not fill it with a chart.
- **Retidão do percurso:** a 130×76 shape (`--blue-600` path + dashed `--amber-500` chord)
  next to the ratio in Saira 44px, with a plain-language explanation of net ÷ path length.
- **Direção:** `--gradient-ink` card with the direction, a 4px confidence bar, and the
  reason in mono 10px `#93A4AB`.
- **Manobras:** Saira 52px count + a paragraph stating the detection rule (sharp direction
  change *with* a clear speed drop and recovery).
- **Técnica de onda · leitura do modelo:** the 3px `--accent` left-border LLM panel,
  `prose.wave` at 13.5px/1.75, signature below.

---

## Interactions & Behavior

| Trigger | Result |
|---|---|
| Tab click | `state.level` → `sessions` \| `session` \| `wave`; section swaps with `mf-fade-up`; chart grow animation replays **once per level visit** (guarded by `this._lvl`) |
| "Compreendi" | `banner: false` |
| Stat tile click | `state.stat = id`; breakdown panel opens under the grid |
| Order toggle / regression toggle | `ordem` tempo⇄spot (cross-fades the two chart groups); `reg` only meaningful while `ordem === 'tempo'` |
| Bivariate / comparative `<select>` | `s3x`/`s3y`, `cmpA`/`cmpB`, `cmpMetric` |
| Comparative hover zones | `hov` drives the overlay group (`cmp.ovCss`) |
| Session row click | opens N2 |
| Map play/pause | `playing`; a **250 ms** interval advances `now` 0→3789, wrapping |
| Map scrubber | `seek` sets `now`, pauses playback |
| Wave mark/dot click | `sel` — isolates that wave, hides the rest, shows the callout |
| Map background click | `clearSel` |
| "Abrir onda" / thumbnail click | `wave = id`, `level = 'wave'` |
| Lock toggle | `unlocked` reveals per-thumbnail delete buttons |
| Thumbnail delete | pushes the id into `del[]` |
| Wave play/pause | `wPlaying`; an **80 ms** interval advances `wNow` by 0.08 s, stops at the end; restarting from the end resets to 0 |
| Wave scrubber | `wNow` (`step 0.1`), pauses |
| Wave `<select>` | `wave` |
| Card hover | tiles lift 5px to a warm shadow; thumbnails flip `rotateY(360deg)`; sessions rows go `--warm-100` |
| Focus | `--focus-ring` (3px `--ring`), inputs/selects switch border to `--accent` |

**Timers use `setInterval`, not `requestAnimationFrame`** — rAF is throttled/paused in a
hidden or background frame, which would freeze the counters at zero. Keep that behavior.

**Reduced motion:** the design system requires all motion to respect
`prefers-reduced-motion` — the prototype does not yet gate the intervals. Add that in
implementation.

---

## State Management

```
level      'sessions' | 'session' | 'wave'
wave       number          // selected wave id
banner     boolean         // method banner visible
now        number 0..3789  // session playhead, seconds
playing    boolean
s3x, s3y   metric ids      // bivariate axes
cx, cy     metric ids
cmpA, cmpB session ids ; cmpMetric metric id
wcx, wcy   metric ids
sel        wave id | null  // isolated wave on the map
swellOn    boolean         // radial swell overlay
mapReady   boolean         // basemap tile probe result
anim       0..1            // chart grow progress
hov        hover key | null
del        wave id[]       // soft-deleted thumbnails
unlocked   boolean         // delete affordances visible
wPlaying   boolean ; wNow  float seconds (sub-second, 0.08 steps)
stat       tile id | null  // open breakdown
ordem      'tempo' | 'spot'
reg        boolean         // regression line
```

**Props (tweakable states, for review):**
- `offline: boolean` — no network, no local model: all LLM prose is replaced by an
  explicit unavailable message and the signature reads *"indisponível — sem rede, sem chave"*.
  The stats are unaffected, and the copy says so.
- `poucasSessoes: boolean` — fewer than 3 sessions: the level card becomes the empty state.

**Data requirements:** one `ActivitySummary` per session, `WaveCandidate[]` per session,
1 Hz sample rows (`t, lat/lon → x/y metres, v, hr, obs`), a marine API swell payload
(which may be partial), and three LLM prose strings. `obs: false` rows must stay in the
array — the blind rail and the dashed/solid split are computed from them.

---

## Design Tokens

All values come from the MF Concepts design system; the token CSS is bundled at
`prototype/_ds/.../tokens/`. Style against the **semantic aliases**, never raw hex.

**Brand**
| Token | Value | Role |
|---|---|---|
| `--amber-500` | `#E8951C` | brand amber / `--primary` — creativity, the "doing" color |
| `--blue-500` | `#2FA8E6` | brand tech blue / `--accent` — future, links, focus |
| `--ink-800` | `#122832` | wordmark ink / `--text` |
| `--warm-50` | `#FBF7F0` | page background / `--bg` |
| `--warm-0` | `#FFFFFF` | `--surface` |

**Ramps used in this product**
Amber `50 #FDF6E9 · 100 #FBE9C4 · 200 #F8D89A · 300 #F4C25C · 400 #F2A024 · 500 #E8951C · 600 #C9760F · 700 #A85C0C · 800 #7E4309 · 900 #5A2F08`
Blue `50 #EAF6FD · 100 #C9E8FA · 200 #9FD7F4 · 300 #6BC2EC · 400 #3FAEE4 · 500 #2FA8E6 · 600 #1E86C4 · 700 #166697 · 800 #114E73 · 900 #0E3A55`
Warm `100 #F4EDE1 · 200 #E9DECC · 300 #D6C7AE · 400 #B3A084 · 500 #877A64`
Ink `900 #0E1F26 · 800 #122832 · 700 #1B3A46 · 600 #2A5160 · 500 #3E6B7C`
Signal `--success #4A7C59 / --success-soft #E3EEE5 · --danger #D2452F / --danger-soft #FBE3DE`

**Semantic aliases**
`--text --ink-800` · `--text-muted --warm-500` · `--text-subtle --warm-400` ·
`--surface --warm-0` · `--surface-2 --warm-100` · `--border --warm-200` ·
`--border-strong --warm-300` · `--primary-hover --amber-600` · `--accent-hover --blue-600` ·
`--ring color-mix(in oklch, var(--blue-500) 55%, transparent)`

**Product-specific colors** (not in the system — introduced by this design, keep them)
| Value | Role |
|---|---|
| `#3E6B7C` (= `--ink-500`) at .32–.45, dashed `4 4`/`5 4` | **estimated** GPS |
| `#8ED2F2` | crest gradient stop, inner face |
| `#FFFFFF` @ .95 | the foam lip at the crest |
| `#93A4AB` | muted text on ink panels |
| `#5E7178` | subtle text on ink panels |

**Gradients**
- `--gradient-brand` `linear-gradient(100deg, #E8951C 0%, #F2A024 38%, #2FA8E6 100%)` — masthead rule + banner strip only.
- `--gradient-ink` `linear-gradient(165deg, #1B3A46 0%, #0E1F26 100%)` — emphasis panels.
- `#wp-crest`, `#wp-vfade`, `#wp-shore` — the wave profile SVG defs, spelled out above.

**Type** — Display **Saira**, Body **Hanken Grotesk**, Mono **DM Mono**.
Scale `--text-2xs 11 · xs 12 · sm 14 · base 16 · md 18 · lg 20 · xl 24 · 2xl 30 · 3xl 38 · 4xl 48 · 5xl 62 · 6xl 80 · 7xl 104`.
Leading `tight 1.04 · snug 1.18 · normal 1.5 · relaxed 1.72`.
Tracking `tighter -.03em · tight -.015em · wide .04em · label .16em · loose .24em`.
Mono labels are **always uppercase + wide-tracked**, 9–11px in this product.

**Coverage → type weight** (the honesty rule, `numCss(cov, size)`):
```
cov >= 0.60 → font-weight 600, opacity 1
cov >= 0.25 → font-weight 500, opacity 0.72
else        → font-weight 400, opacity 0.50
```
Paired with a coverage arc whose stroke is `--blue-600` / `--amber-500` / `--warm-400`
on the same thresholds.

**Spacing** 4px grid, `--space-1 4 … --space-32 128`. Used gaps: 12/14/18/26px; card
padding 20–24px; section headers `40px 0 18px`.

**Radii** `--radius-xs 3 · sm 6 · md 10 · lg 16 (cards) · xl 24 · full 999`.

**Borders** `--border-thin 1px · --border-med 1.5px · --border-thick 2px`.

**Elevation**
`--shadow-xs 0 1px 2px rgba(18,40,50,.06)` ·
`--shadow-sm 0 1px 3px rgba(18,40,50,.08), 0 1px 2px rgba(18,40,50,.05)` ·
`--shadow-md 0 4px 12px rgba(18,40,50,.10), 0 2px 4px rgba(18,40,50,.06)` ·
`--shadow-lg 0 12px 28px rgba(18,40,50,.12), 0 6px 10px rgba(18,40,50,.07)` ·
`--focus-ring 0 0 0 3px var(--ring)`. Shadows are warm-tinted on the ink hue, never black.

**Motion** `--dur-fast 140ms · base 240ms · slow 420ms`,
`--ease-out cubic-bezier(.22,1,.36,1)`. Signature entrance `mf-fade-up`.
Product-specific: chart cross-fade `transform .55s cubic-bezier(.22,1,.36,1), opacity .4s linear`;
chart grow 900ms cubic ease-out; session clock 250 ms/step; wave clock 80 ms/0.08 s.

---

## Voice & copy rules

The UI copy is Portuguese and follows the MF Concepts voice: calm, specific, quantified,
no emoji, mono uppercase eyebrows carrying the technical register. Two product rules on top:

1. **Never state a number the data can't support.** Say what is measured, what is
   estimated, and what is missing — in words, next to the chart.
2. **LLM output is always marked and signed.** Amber/blue accent panel, mono signature
   line naming the model and where it ran.

Exact strings for every label and paragraph are in the prototype; lift them verbatim.

---

## Assets

| Asset | Source |
|---|---|
| `prototype/assets/logo-mark.png` | MF Concepts design system `assets/` — used at 34×34 in the masthead |
| `prototype/assets/logo-lockup-dark.png` | MF Concepts design system `assets/` — not used on screen, included for completeness |
| OSM raster tiles `tile.openstreetmap.org/17/{x}/{y}.png` | Basemap under the track map. **Attribution is required** and is currently missing — add it in implementation, or swap for the codebase's existing tile provider. |
| Fonts Saira / Hanken Grotesk / DM Mono | Loaded by `_ds/.../tokens/fonts.css` |
| Icons | Inline SVG, Lucide-style: 2px round-cap/round-join stroke, `currentColor`. No icon font, no emoji. |

---

## Files

```
design_handoff_surf_analytics/
├── README.md                          ← this document
├── source-repo.md                     ← repo, branch, last sync, screen→source map
└── prototype/
    ├── Surf Analytics.dc.html         ← the v1.0 design (all three levels)
    ├── support.js                     ← prototype runtime (not for production)
    ├── assets/                        ← logo files used by the design
    └── _ds/mf-concepts-design-system-…/
        ├── styles.css                 ← single entry point
        ├── _ds_bundle.js              ← Button / Badge / Card / Tabs / … components
        ├── _ds_manifest.json, readme.md
        └── tokens/ fonts · colors · typography · spacing · elevation · base
```

Also in the project, not part of this handoff but related:
`Surf Analytics (estilo instrumento).dc.html` (an alternative instrument-panel visual
direction) and `Surf Drill-Down.dc.html` (an earlier drill-down study).

---

## Implementation checklist

- [ ] Recreate the three levels with the codebase's own components; keep the 1440px desktop frame.
- [ ] Wire real `ActivitySummary` / `WaveCandidate` / 1 Hz sample data; keep `obs: false` rows.
- [ ] Implement measured / estimated / blind as solid / dashed-translucent / absence + blind rail.
- [ ] Implement `numCss` coverage→weight/opacity and the coverage arcs.
- [ ] Wave profile: GPS axes, inferred coastline, 136px crest with the exact gradient stops, −6.6° rotation, Catmull–Rom interpolation at 80 ms, surfer 8px ahead of the crest.
- [ ] **Decide the 1:1 aspect-ratio question** for the wave profile.
- [ ] Keep the reserved bottom-turn placeholder empty.
- [ ] Mark and sign every LLM string; handle the offline state.
- [ ] Add OSM attribution.
- [ ] Gate all motion behind `prefers-reduced-motion`.
