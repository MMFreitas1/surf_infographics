"use client";

/**
 * Playback, and the ribbon that says what each second of the session was.
 *
 * **250 ms per step**, from the design. A surf session is an hour of mostly sitting, so real
 * time is unwatchable and a slider alone tells you nothing about rhythm; a quarter-second
 * step is fast enough to show the shape of the session and slow enough to follow a ride.
 *
 * The ribbon and the **blind rail** are the screen's honesty made structural. The ribbon
 * carries what the session *was* — riding, or not — and the rail underneath carries what the
 * watch *saw*. Keeping them on separate rows is the point: a wave and a blind window are not
 * alternatives, and a session can be both at once. Painting them into one strip would force
 * a choice between two facts that are both true.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useT } from "@/lib/i18n";
import type { SmoothedSample, WaveVerdict } from "@/lib/schema";
import { formatClock, spansWhere } from "@/lib/trace";

const STEP_MS = 250;

interface Props {
  samples: SmoothedSample[];
  waves: WaveVerdict[];
  now: number;
  onNow: (t: number) => void;
  selected: WaveVerdict | null;
  onSelect: (wave: WaveVerdict | null) => void;
}

export function Playback({ samples, waves, now, onNow, selected, onSelect }: Props) {
  const t = useT();
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const start = samples[0]?.t ?? 0;
  const end = samples.at(-1)?.t ?? start;
  const span = Math.max(1, end - start);

  const stop = useCallback(() => {
    if (timer.current !== null) clearInterval(timer.current);
    timer.current = null;
    setPlaying(false);
  }, []);

  // The interval closes over `now` at the moment it was created, so reading it through a ref
  // is what stops playback freezing on the second it started at.
  const nowRef = useRef(now);
  nowRef.current = now;

  useEffect(() => {
    if (!playing) return;
    timer.current = setInterval(() => {
      onNow(Math.min(end, nowRef.current + 1));
    }, STEP_MS);
    return () => {
      if (timer.current !== null) clearInterval(timer.current);
      timer.current = null;
    };
  }, [playing, end, onNow]);

  useEffect(() => {
    if (playing && now >= end) stop();
  }, [playing, now, end, stop]);

  const { blind, ridden } = useMemo(
    () => ({
      blind: spansWhere(samples, false),
      ridden: waves.filter((w) => w.is_wave),
    }),
    [samples, waves],
  );

  const pct = (value: number) => `${((value - start) / span) * 100}%`;
  const width = (from: number, to: number) => `${((to - from) / span) * 100}%`;

  return (
    <div className="playback">
      <div className="playback-controls">
        <button
          type="button"
          className="play-button"
          onClick={() => (playing ? stop() : setPlaying(true))}
          aria-label={playing ? t("playback.pause") : t("playback.play")}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <span className="clock">{formatClock(now, start)}</span>
        <input
          type="range"
          className="scrubber"
          min={start}
          max={end}
          step={1}
          value={now}
          aria-label={t("playback.scrub")}
          onChange={(event) => {
            stop();
            onNow(Number(event.target.value));
          }}
        />
        <span className="step-note">{t("playback.step")}</span>
      </div>

      {/* Row one: what the session was. Row two: what the watch saw. Never merged. */}
      <div className="ribbon" aria-hidden="true">
        {ridden.map((wave) => (
          <button
            type="button"
            key={wave.t_start}
            className={
              selected !== null && selected.t_start === wave.t_start
                ? "ribbon-wave ribbon-wave-selected"
                : "ribbon-wave"
            }
            style={{ left: pct(wave.t_start), width: width(wave.t_start, wave.t_end) }}
            onClick={() => onSelect(selected?.t_start === wave.t_start ? null : wave)}
            // Coverage reaches the ribbon too: a ride the watch barely saw is drawn fainter
            // than one it watched throughout, so the strip cannot flatten the two.
            data-coverage={wave.position_coverage < 0.25 ? "low" : "ok"}
          />
        ))}
        <span className="playhead" style={{ left: pct(now) }} />
      </div>
      <div className="blind-rail" aria-hidden="true">
        {blind.map((gap) => (
          <span
            key={gap.t_start}
            className="blind-span"
            style={{ left: pct(gap.t_start), width: width(gap.t_start, gap.t_end) }}
          />
        ))}
      </div>
      <p className="ribbon-key">
        <span className="key key-wave" /> {t("legend.wave")}
        <span className="key key-blind" /> {t("legend.blind")}
      </p>
    </div>
  );
}
