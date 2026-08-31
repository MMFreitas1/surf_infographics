"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  completePass,
  getCandidates,
  getLabels,
  getPasses,
  getTrack,
  postLabel,
} from "@/lib/api";
import type { SessionCandidates, SessionTrack, StoredLabel } from "@/lib/schema";
import { coverageOf, formatClock, type Span, spansWhere } from "@/lib/trace";
import { type Draft, LabelPanel } from "./label-panel";
import { type Band, TracePanel } from "./trace-panel";

// deck.gl touches the DOM and WebGL on import, neither of which exists during SSR.
const TrackMap = dynamic(() => import("./track-map").then((m) => m.TrackMap), {
  ssr: false,
  loading: () => <section className="panel map-placeholder">loading map…</section>,
});

const SCRUB_STEP = 1;
const SCRUB_JUMP = 10;

/**
 * The labeling workspace.
 *
 * The blind/assisted split (ADR-0012) is visible here as an absence: `candidates` stays null
 * and is never fetched until a blind pass exists for this session *and* the labeller has
 * explicitly switched into assisted mode. The server refuses assisted labels without that
 * pass anyway — this is the same rule expressed as something the labeller can see.
 */
export function SessionView({ activityId }: { activityId: string }) {
  const [track, setTrack] = useState<SessionTrack | null>(null);
  const [labels, setLabels] = useState<StoredLabel[]>([]);
  const [proposals, setProposals] = useState<SessionCandidates | null>(null);
  const [blindPassDone, setBlindPassDone] = useState(false);
  const [assisted, setAssisted] = useState(false);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [now, setNow] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const [loaded, stored, passes] = await Promise.all([
          getTrack(activityId),
          getLabels(activityId),
          getPasses(activityId),
        ]);
        if (!live) return;
        setTrack(loaded);
        setLabels(stored);
        setBlindPassDone(passes.some((p) => p.kind === "blind"));
        setNow(loaded.smoothed[0]?.t ?? 0);
      } catch (cause) {
        if (live) setError(cause instanceof ApiError ? cause.message : String(cause));
      }
    })();
    return () => {
      live = false;
    };
  }, [activityId]);

  const domain = useMemo<[number, number]>(() => {
    const rows = track?.smoothed ?? [];
    return [rows[0]?.t ?? 0, rows[rows.length - 1]?.t ?? 1];
  }, [track]);

  const start = domain[0];

  // Playback. One real second per session second; the point is to re-watch a stretch, not
  // to sit through an hour, so the labeller scrubs and the clock only fills the gaps.
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setNow((t) => (t + 1 > domain[1] ? domain[1] : t + 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [playing, domain]);

  const seek = useCallback(
    (t: number) => setNow(Math.min(Math.max(t, domain[0]), domain[1])),
    [domain],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) {
        return;
      }
      const step = event.shiftKey ? SCRUB_JUMP : SCRUB_STEP;
      if (event.key === "ArrowLeft") seek(now - step);
      else if (event.key === "ArrowRight") seek(now + step);
      else if (event.key === " ") {
        event.preventDefault();
        setPlaying((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [now, seek]);

  const enterAssisted = async () => {
    try {
      setProposals(await getCandidates(activityId));
      setAssisted(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
    }
  };

  const addDraft = useCallback(
    (span: Span, supersedes: string | null = null) => {
      setDrafts((existing) => [
        ...existing,
        {
          id: crypto.randomUUID(),
          span,
          is_wave: true,
          direction: "unknown",
          note: "",
          coverage: coverageOf(track?.smoothed ?? [], span),
          supersedes,
        },
      ]);
    },
    [track],
  );

  const save = async (index: number) => {
    const draft = drafts[index];
    if (!draft) return;
    setSaving(true);
    try {
      const stored = await postLabel(activityId, {
        t_start: draft.span.t_start,
        t_end: draft.span.t_end,
        is_wave: draft.is_wave,
        // A person drew this deliberately, so it is verified. The "unsure" case is a note,
        // not a silently uncounted label.
        verified: true,
        source: assisted ? "human_assisted" : "human",
        direction: draft.direction,
        note: draft.note,
        supersedes: draft.supersedes,
      });
      setLabels((rows) => [...rows, stored]);
      setDrafts((rows) => rows.filter((_, i) => i !== index));
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  };

  const finishPass = async () => {
    setSaving(true);
    try {
      const completed = await completePass(activityId, assisted ? "assisted" : "blind");
      if (completed.kind === "blind") setBlindPassDone(true);
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  };

  // Memoised because TracePanel rebuilds its chart whenever these change identity, and a
  // fresh array on every render would mean rebuilding the plot on every render — forever.
  const speed = useMemo(
    () =>
      (track?.smoothed ?? []).map((row) => ({
        t: row.t,
        y: row.speed_ms,
        observed: row.observed,
      })),
    [track],
  );
  const crossShore = useMemo(
    () =>
      (track?.framed ?? []).map((row) => ({
        t: row.t,
        y: row.v_cross_ms,
        observed: row.observed,
      })),
    [track],
  );
  const sigma = useMemo(
    () =>
      (track?.smoothed ?? []).map((row) => ({
        t: row.t,
        y: row.position_sigma_m,
        observed: row.observed,
      })),
    [track],
  );

  if (error && !track) {
    return (
      <main className="workspace">
        <p className="error">{error}</p>
        <Link href="/">← all sessions</Link>
      </main>
    );
  }
  if (!track) return <main className="workspace">loading session…</main>;

  const blind = spansWhere(track.smoothed, false);
  const bands: Band[] = [
    ...blind.map(
      (span): Band => ({
        id: `blind-${span.t_start}`,
        span,
        kind: "blind",
        title: "no GPS fix",
      }),
    ),
    ...labels
      .filter((label) => !labels.some((other) => other.supersedes === label.label_id))
      .map(
        (label): Band => ({
          id: label.label_id,
          span: { t_start: label.t_start, t_end: label.t_end },
          kind: label.is_wave ? "saved" : "rejected",
          title: label.note || (label.is_wave ? "ride" : "not a ride"),
        }),
      ),
    ...drafts.map((draft): Band => ({ id: draft.id, span: draft.span, kind: "draft" })),
    ...(assisted && proposals
      ? proposals.candidates.map(
          (candidate): Band => ({
            id: `candidate-${candidate.t_start}`,
            span: { t_start: candidate.t_start, t_end: candidate.t_end },
            kind: "candidate",
            title: `${Math.round(candidate.position_coverage * 100)}% measured`,
          }),
        )
      : []),
  ];

  return (
    <main className="workspace">
      <header className="workspace-head">
        <div>
          <Link href="/">← all sessions</Link>
          <h1>
            {assisted ? "Assisted pass" : "Blind pass"} · {formatClock(now, start)}
          </h1>
        </div>
        <div className="row">
          <button type="button" onClick={() => setPlaying((p) => !p)}>
            {playing ? "Pause" : "Play"}
          </button>
          {assisted ? (
            <span className="tag tag-assisted">candidates visible</span>
          ) : blindPassDone ? (
            <button type="button" onClick={enterAssisted}>
              Reveal candidates
            </button>
          ) : (
            <span className="muted" title="ADR-0012">
              candidates unlock after the blind pass
            </span>
          )}
        </div>
      </header>

      {error ? <p className="error">{error}</p> : null}

      <div className="columns">
        <div className="panels">
          <TracePanel
            title="Speed"
            unit="m/s"
            points={speed}
            domain={domain}
            bands={bands}
            now={now}
            onSelect={(span) => addDraft(span)}
            onScrub={seek}
          />
          <TracePanel
            title="Cross-shore velocity"
            unit="m/s · + is shoreward"
            points={crossShore}
            domain={domain}
            bands={bands}
            now={now}
            zeroLine
            caveat={
              track.frame.reliable
                ? `shore bearing ${track.frame.shore_bearing_deg.toFixed(0)}°`
                : `unreliable frame — coherence ${track.frame.coherence.toFixed(2)}. The shore axis is a guess on this session, so treat this panel as indicative only (ADR-0011).`
            }
            onSelect={(span) => addDraft(span)}
            onScrub={seek}
          />
          <TracePanel
            title="Position uncertainty"
            unit="metres"
            points={sigma}
            domain={domain}
            bands={bands}
            now={now}
            area
            height={80}
            onScrub={seek}
          />
          <TrackMap samples={track.smoothed} frame={track.frame} now={now} />
        </div>

        <LabelPanel
          start={start}
          drafts={drafts}
          saved={labels}
          candidates={proposals?.candidates ?? null}
          assisted={assisted}
          saving={saving}
          onChange={(i, draft) => setDrafts((rows) => rows.map((r, j) => (j === i ? draft : r)))}
          onDiscard={(i) => setDrafts((rows) => rows.filter((_, j) => j !== i))}
          onSave={save}
          onCorrect={(label) =>
            addDraft({ t_start: label.t_start, t_end: label.t_end }, label.label_id)
          }
          onSeek={seek}
          onFinishPass={finishPass}
        />
      </div>
    </main>
  );
}
