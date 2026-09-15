# MF Concepts — Design System

> Art fused with technology. The warm hand of a maker meeting a cool, futuristic horizon.

This is the design system for **MF Concepts** — a solopreneur studio that builds creative software and, in time, intends to branch into machines and robotics. It encodes the brand's identity (colors, type, logo, voice) and ships a small, brand-styled component library plus full-screen UI kits, so any agent or developer can produce on-brand interfaces and assets.

---

## 1 · The company

MF Concepts mirrors its founder's craftiness, passion for building solutions, and creative freedom. It began as **MF Concepts | Photography** (services + skill-building) with a deliberate roadmap to evolve:

```
Photography  →  Technology  →  Machines
(proven)        (current)       (next branch)
```

The operating mindset is **MVP → prove it → branch**: ship a creative app that solves a real problem, validate it, then extend into the next branch. The studio serves **SMEs**, with a specialist's ambition in **Computer Vision and image processing** — a scarce, high-craft discipline the founder wants to own.

**We are currently in the Technology phase.** Products are creative apps that solve problems; the long arc reaches toward repurposing/retraining LLMs, then physical machines, components, and robotics.

### Brand colors, in the founder's words
- **Warm colors, yellow → amber** symbolize *creativity* and the *desire to create*.
- A small hint of **tech light blue** symbolizes a *future outlook* and *harmony* — futuristic but *integrated, not violent*; contrasting with the natural while staying part of it.
- Amber and the tech blue are **opposite on the color wheel** by design — the tension drives the viewer's eye and engagement, and signals *art fused with technology*.

---

## 2 · Sources

This system was built from materials the founder provided. You may not have access to all of them; they are recorded here in case you do.

- **Logo artwork** — provided as PNG/TIF: the bearded-maker mark (amber hair/beard, blue camera-lens sunglasses) plus horizontal, vertical, white-letter, and **Technology** sub-brand lockups. Copied into [`assets/`](./assets).
- **GitHub — [`MMFreitas1/curriculum_vitae`](https://github.com/MMFreitas1/curriculum_vitae)** — the founder's CV website. The authoritative existing surface; the source of the voice/tone, the mono-eyebrow + warm-neutral aesthetic, the `fadeUp` motion, and the portrait/surf imagery. Explore it to design more faithfully against the brand.
  - Other repos on the account (private) — `gps-tracker-animator`, `andy_surf_analysis`, analysis projects — corroborate the CV / Computer Vision focus but were not used directly.

> If you have access to these and want higher fidelity, read them and lift exact values rather than relying on this summary.

---

## 3 · Content fundamentals (voice & tone)

The brand voice is **a maker's, not a brochure's** — an engineer's precision with an artist's eye.

- **Confident, direct, specific.** Concrete verbs — *built, deployed, architected, shipped, trained* — never *leveraged / streamlined / synergized*.
- **Numbers over superlatives.** "+40% accuracy", "10–18× faster", "$0.005 / call" — quantify the claim instead of praising it.
- **First person, lightly.** "I build creative apps that solve problems." Speaks as an individual maker; addresses the client as *you* when selling. Avoids corporate *we* inflation.
- **Technical without jargon-for-its-own-sake.** Computer vision, image processing, MVPs, branches — real terms, plainly used.
- **Calm and intentional.** Short sentences. One idea per line. Lots of breathing room (the CV uses wide 8vw gutters).
- **No emoji.** The technical register is carried by **mono-set, uppercase, wide-tracked eyebrows** (e.g. `COMPUTER VISION · EST. 2024`, `PHASE — TECHNOLOGY`), not by decoration.
- **Casing:** Title or sentence case for headings; UPPERCASE only for mono eyebrows/labels. Never all-caps body.

**Example copy**
- Eyebrow: `— PHASE: TECHNOLOGY`
- Headline: *Build creative tools that solve real problems.*
- Body: *A solopreneur studio building creative apps for SMEs — with the rigor of an engineer and the eye of a photographer. Each product is an MVP: prove it, then branch.*

---

## 4 · Visual foundations

**Color.** A deliberate **complementary pairing** anchored by ink.
- **Amber** (`--amber-500` `#E8951C`, hue ≈ 40°) — creativity, the "doing" color, primary actions.
- **Tech blue** (`--blue-500` `#2FA8E6`, hue ≈ 205°) — future/vision, the accent, focus, links.
- **Ink** (`--ink-800` `#122832`) — the teal-navy of the wordmark; the unifier and primary text. Bluish enough to belong to the tech side, dark enough to ground the warmth.
- **Neutrals are warm** — cream paper (`--warm-50` `#FBF7F0`), never clinical gray.
- Use the **`--gradient-brand`** amber→blue sweep deliberately (hero accents, a single bar), never as a filler background. Dark theme via `[data-theme="dark"]` flips to an ink surface with warm text.

**Type.** Three families.
- **Display — Saira** (wide, squared, monoline technical sans): headings + brand text. A close stand-in for the logo's lettering. Tighten tracking at large sizes.
- **Body — Hanken Grotesk** (warm humanist grotesque): running text + UI.
- **Mono — DM Mono**: eyebrows, labels, metadata, data readouts — always uppercase + wide tracking as a label. *(Carried from the CV.)*
- Scale is a ~1.25 major-third ramp (`--text-xs` 12 → `--text-7xl` 104). On 1920×1080 slides keep text ≥ 24px.

**Spacing & shape.** 4px grid (`--space-*`). Radii are **soft-squared**, matching the wordmark — `--radius-md` 10 (buttons/inputs), `--radius-lg` 16 (cards); reserve `--radius-full` for avatars/switches/dots. Pages favor generous side gutters (`--gutter` 8vw).

**Elevation.** Shadows are **warm-tinted** (built on the ink hue, never pure black) and soft. Two **signature glows** — `--glow-amber` and `--glow-blue` — are reserved for emphasis/focus, not everyday cards. A default **card** is `--surface` (white) + 1px `--border` + `--shadow-sm` + `--radius-lg`; `tone="ink"` flips it to the dark gradient; an optional top hairline `accent` marks it amber or blue.

**Backgrounds & texture.** Warm cream by default; ink for emphasis panels and dark mode. No busy patterns. An optional fine-grain film overlay (`.mf-grain`, from the CV) adds subtle texture on hero/full-bleed areas. Imagery skews **warm** (golden-hour photography), echoing the amber half of the palette.

**Motion.** Calm and intentional — short fades and a gentle rise (`@keyframes mf-fade-up`, the CV's signature), eased with `--ease-out` `cubic-bezier(.22,1,.36,1)`. Durations `--dur-fast` 140 → `--dur-slow` 420. **Nothing bounces, nothing loops.** All motion respects `prefers-reduced-motion`.

**Interaction states.**
- *Hover:* darken the fill one step (`--primary-hover`), or fill the surface on ghost/secondary; cards lift `-3px` to `--shadow-lg`.
- *Press:* a small scale-down (`translateY(1px) scale(.99)` on buttons, `scale(.92)` on icon buttons) — tactile, not springy.
- *Focus:* the blue tech ring — `--focus-ring` (3px `--ring`). Inputs switch their border to `--accent` on focus.
- *Selection:* amber highlight (`--amber-200`).

**Borders.** Hairline `1px` `--border` (warm) for separation; `1.5px` `--border-strong` for inputs/controls. Lines, not heavy boxes.

---

## 5 · Iconography

- **No bespoke icon set ships with this system.** The recommended set is **[Lucide](https://lucide.dev)** — its **2px round-cap, round-join** stroke style matches the wordmark's monoline character and the components' geometry. Component cards in this project draw small inline Lucide-style SVGs to demonstrate.
- **Usage:** outline (stroke) icons at `1.75–2px`, sized 16–20px inline with text; color `currentColor` so they inherit. Pass them to `Button.iconLeft/iconRight`, `IconButton`, and `Tabs` items as nodes.
- **Emoji:** never. **Unicode glyphs:** sparingly (e.g. `★` to mark a brand swatch, `×` to dismiss a tag) — not as UI icons.
- **The logo is not an icon.** Use the lockups in `assets/` for brand presence; don't redraw the mark inline. Substitution flag: if you need a Lucide icon offline, link it from CDN or copy the specific SVG in — don't hand-roll an approximation.

---

## 6 · Logo & brand assets

Stored in [`assets/`](./assets):

| File | Use |
|---|---|
| `logo-mark.png` | The bearded-maker mark alone |
| `logo-lockup-dark.png` | Horizontal lockup, dark letters — primary on light |
| `logo-lockup-white.png` | Horizontal lockup, white letters — on ink/photography |
| `logo-lockup-technology.png` | **Technology** sub-brand lockup, on dark |
| `wordmark-vertical.png` | Vertical/stacked lettering |
| `photo-portrait.jpg`, `photo-surf.jpg` | Founder imagery (from the CV) for kit hero/about use |

**Clearspace:** keep ≥ ½ the mark's height clear on all sides. **Don't** recolor the beard/lens, stretch, or place the dark-letter lockup on a busy/dark ground (use the white or Technology variant).

> **Logo exploration in progress.** [`explorations/Logo Explorations.html`](./explorations/Logo%20Explorations.html) contains eight redesign directions across four levels of abstraction (refined likeness → symbolic fusion → monogram → pure abstraction), each keeping the lens/amber→blue/maker DNA but scaling better than the literal portrait. Awaiting the founder's pick before the chosen mark is promoted into `assets/`.

---

## 7 · Index / manifest

**Root**
- `styles.css` — the single entry point consumers link. `@import`s only.
- `tokens/` — `fonts.css`, `colors.css`, `typography.css`, `spacing.css`, `elevation.css`, `base.css`.
- `assets/` — logos + imagery (above).
- `guidelines/` — foundation specimen cards (the Design System tab).
- `components/` — reusable React primitives.
- `explorations/` — the in-progress logo study.
- `SKILL.md` — Agent-Skill manifest for use in Claude Code.

**Components** (`window.MFConceptsDesignSystem_…`)
- `components/core/` — **Button**, **IconButton**, **Badge**, **Tag**, **Avatar**, **Card**
- `components/forms/` — **Input**, **Switch**
- `components/navigation/` — **Tabs**

Each component is `Name.jsx` + `Name.d.ts` + `Name.prompt.md`, with one `@dsCard` demo HTML per directory. Style strictly via the CSS custom properties — no hard-coded hex.

**Foundation cards** (`guidelines/`) — brand pairing, amber & blue ramps, warm neutrals + ink, semantic roles, display/body/mono type, spacing/radii/elevation, logo lockups, mark + clearspace, gradient + voice.

**Planned (not yet built):** marketing-website UI kit, creative CV/Vision-app UI kit. *(In progress — the logo redesign was prioritized first.)*

---

## 8 · How to use

1. **Link** `styles.css` for tokens + fonts.
2. **Compose** with the components via `window.MFConceptsDesignSystem_…` (see each `.prompt.md`).
3. **Design against the semantic aliases** (`--primary`, `--accent`, `--text`, `--surface`, `--border`), not the raw ramps.
4. **Hold the voice** — specific, quantified, calm; mono eyebrows; no emoji.
5. **One amber `primary` per view** — it's the loudest element in the system; let blue carry "forward/tech" and ink carry structure.
