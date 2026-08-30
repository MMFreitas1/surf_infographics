"use client";

import type { StoredLabel, WaveCandidate } from "@/lib/schema";
import { formatClock, formatDuration, type Span } from "@/lib/trace";

/** A span the labeller has drawn but not yet committed. */
export interface Draft {
  id: string;
  span: Span;
  is_wave: boolean;
  direction: "left" | "right" | "straight" | "unknown";
  note: string;
  coverage: number;
  supersedes: string | null;
}

interface Props {
  start: number;
  drafts: Draft[];
  saved: StoredLabel[];
  candidates: WaveCandidate[] | null;
  assisted: boolean;
  saving: boolean;
  onChange: (index: number, draft: Draft) => void;
  onDiscard: (index: number) => void;
  onSave: (index: number) => void;
  onCorrect: (label: StoredLabel) => void;
  onSeek: (t: number) => void;
  onFinishPass: () => void;
}

/**
 * The right-hand column: what has been marked, and what is still a draft.
 *
 * Coverage is shown on every draft before it is saved, because a person who has just drawn
 * a wave across a stretch the watch was blind through should be told so while they can still
 * change their mind — not discover it in a metric three phases later.
 */
export function LabelPanel({
  start,
  drafts,
  saved,
  candidates,
  assisted,
  saving,
  onChange,
  onDiscard,
  onSave,
  onCorrect,
  onSeek,
  onFinishPass,
}: Props) {
  const current = saved.filter(
    (label) => !saved.some((other) => other.supersedes === label.label_id),
  );

  return (
    <aside className="labels">
      <section>
        <h2>Drafts</h2>
        {drafts.length === 0 ? <p className="muted">Drag across a trace to mark a wave.</p> : null}
        {drafts.map((draft, i) => (
          <article className="draft" key={draft.id}>
            <header>
              <button type="button" className="link" onClick={() => onSeek(draft.span.t_start)}>
                {formatClock(draft.span.t_start, start)} – {formatClock(draft.span.t_end, start)}
              </button>
              <span className="muted">{formatDuration(draft.span.t_end - draft.span.t_start)}</span>
            </header>

            <p className={draft.coverage < 0.5 ? "coverage warn" : "coverage"}>
              {Math.round(draft.coverage * 100)}% of this was actually measured
              {draft.coverage === 0 ? " — the watch saw none of it" : ""}
            </p>

            <label>
              <input
                type="checkbox"
                checked={draft.is_wave}
                onChange={(e) => onChange(i, { ...draft, is_wave: e.target.checked })}
              />
              this is a ride
            </label>

            <select
              value={draft.direction}
              onChange={(e) =>
                onChange(i, { ...draft, direction: e.target.value as Draft["direction"] })
              }
            >
              <option value="unknown">direction unknown</option>
              <option value="left">left</option>
              <option value="right">right</option>
              <option value="straight">straight</option>
            </select>

            <input
              type="text"
              placeholder="note (optional)"
              value={draft.note}
              onChange={(e) => onChange(i, { ...draft, note: e.target.value })}
            />

            <div className="row">
              <button type="button" onClick={() => onSave(i)} disabled={saving}>
                Save
              </button>
              <button type="button" className="quiet" onClick={() => onDiscard(i)}>
                Discard
              </button>
            </div>
          </article>
        ))}
      </section>

      <section>
        <h2>
          Saved{" "}
          <span className="muted">
            ({current.length} current, {saved.length} rows)
          </span>
        </h2>
        <ul className="saved">
          {current.map((label) => (
            <li key={label.label_id}>
              <button type="button" className="link" onClick={() => onSeek(label.t_start)}>
                {formatClock(label.t_start, start)} – {formatClock(label.t_end, start)}
              </button>
              <span className={label.is_wave ? "tag tag-wave" : "tag tag-not"}>
                {label.is_wave ? "ride" : "not a ride"}
              </span>
              {label.source === "human_assisted" ? (
                <span className="tag tag-assisted" title="excluded from the metric (ADR-0012)">
                  assisted
                </span>
              ) : null}
              <button type="button" className="quiet" onClick={() => onCorrect(label)}>
                correct
              </button>
            </li>
          ))}
        </ul>
        {saved.length > current.length ? (
          <p className="muted">
            {saved.length - current.length} superseded row
            {saved.length - current.length === 1 ? "" : "s"} kept — corrections never delete.
          </p>
        ) : null}
      </section>

      {assisted && candidates ? (
        <section>
          <h2>
            Proposals <span className="muted">({candidates.length})</span>
          </h2>
          <p className="muted">
            L3 proposes; it does not judge. Confirm or reject each — these are recorded as assisted
            and stay out of the metric.
          </p>
          <ul className="saved">
            {candidates.map((candidate) => (
              <li key={`${candidate.t_start}`}>
                <button type="button" className="link" onClick={() => onSeek(candidate.t_start)}>
                  {formatClock(candidate.t_start, start)} – {formatClock(candidate.t_end, start)}
                </button>
                <span
                  className={candidate.position_coverage === 0 ? "tag tag-blind" : "tag"}
                  title="fraction of the proposal that carried a GPS fix"
                >
                  {Math.round(candidate.position_coverage * 100)}% measured
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <button type="button" className="primary" onClick={onFinishPass} disabled={saving}>
        Finish {assisted ? "assisted" : "blind"} pass
      </button>
    </aside>
  );
}
