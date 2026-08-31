"use client";

import * as Plot from "@observablehq/plot";
import { useCallback, useEffect, useRef, useState } from "react";
import { clampSpan, orderSpan, type Span, withRuns } from "@/lib/trace";

/** One value of one series, and whether the watch saw the second it came from. */
export interface TracePoint {
  t: number;
  y: number;
  observed: boolean;
}

/** A band drawn over the trace. `kind` decides how it reads, not what it means. */
export interface Band {
  id: string;
  span: Span;
  kind: "blind" | "saved" | "rejected" | "draft" | "candidate";
  title?: string;
}

interface Props {
  title: string;
  unit: string;
  points: TracePoint[];
  domain: [number, number];
  bands: Band[];
  now: number;
  height?: number;
  zeroLine?: boolean;
  area?: boolean;
  caveat?: string | null;
  onSelect?: (span: Span) => void;
  onScrub?: (t: number) => void;
}

/** Below this, a drag was a click: the labeller meant to move the playhead, not mark a wave. */
const MIN_DRAG_SECONDS = 1.5;

interface XScale {
  apply: (value: number) => number;
  invert: (px: number) => number;
}

/**
 * One time series, drawn so that a measured second and an invented one cannot be confused.
 *
 * Observable Plot draws the data; the bands, the playhead and the drag surface are HTML on
 * top of it, positioned with the plot's own x scale. That split is deliberate — reading
 * `chart.scale("x")` rather than recomputing margins means the overlay cannot drift out of
 * alignment with the chart underneath it, which is the classic way a labelling tool starts
 * quietly recording the wrong times.
 */
export function TracePanel({
  title,
  unit,
  points,
  domain,
  bands,
  now,
  height = 130,
  zeroLine = false,
  area = false,
  caveat = null,
  onSelect,
  onScrub,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const plotRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [scale, setScale] = useState<XScale | null>(null);
  const [drag, setDrag] = useState<Span | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.floor(entry?.contentRect.width ?? 0));
    });
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const host = plotRef.current;
    if (!host || width === 0) return;

    const runs = withRuns(points);
    const measured = runs.filter((p) => p.series === "measured");
    const estimated = runs.filter((p) => p.series === "estimated");

    const chart = Plot.plot({
      width,
      height,
      marginLeft: 46,
      marginRight: 8,
      marginTop: 6,
      marginBottom: 18,
      x: { domain, axis: null },
      y: { grid: true, label: unit, nice: true },
      marks: [
        zeroLine ? Plot.ruleY([0], { stroke: "currentColor", strokeOpacity: 0.35 }) : null,
        area
          ? Plot.areaY(points, {
              x: "t",
              y: "y",
              fill: "var(--unknown)",
              fillOpacity: 0.5,
            })
          : null,
        // Estimated first, so a measured second is never hidden behind a guess.
        Plot.line(estimated, {
          x: "t",
          y: "y",
          z: "run",
          stroke: "var(--estimated)",
          strokeWidth: 1.25,
          strokeDasharray: "3,3",
        }),
        Plot.line(measured, {
          x: "t",
          y: "y",
          z: "run",
          stroke: "var(--measured)",
          strokeWidth: 1.5,
        }),
      ].filter(Boolean),
    });

    host.replaceChildren(chart);
    const x = chart.scale("x");
    setScale(
      x && typeof x.apply === "function" && typeof x.invert === "function"
        ? { apply: x.apply as (v: number) => number, invert: x.invert as (p: number) => number }
        : null,
    );
    return () => chart.remove();
  }, [points, domain, width, height, unit, zeroLine, area]);

  const timeAt = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!scale) return null;
      const rect = event.currentTarget.getBoundingClientRect();
      return scale.invert(event.clientX - rect.left);
    },
    [scale],
  );

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    const t = timeAt(event);
    if (t === null) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({ t_start: t, t_end: t });
  };

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const t = timeAt(event);
    if (t === null) return;
    setHover(t);
    if (drag) setDrag({ ...drag, t_end: t });
  };

  const onPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const t = timeAt(event);
    if (t === null || !drag) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    const span = clampSpan(orderSpan(drag.t_start, t), domain);
    setDrag(null);
    if (span.t_end - span.t_start >= MIN_DRAG_SECONDS) onSelect?.(span);
    else onScrub?.(span.t_start);
  };

  const left = (t: number) => (scale ? scale.apply(t) : 0);
  const drawn: Band[] = drag ? [...bands, { id: "dragging", span: drag, kind: "draft" }] : bands;

  return (
    <section className="panel">
      <header className="panel-head">
        <h2>{title}</h2>
        {caveat ? <p className="caveat">{caveat}</p> : null}
      </header>
      <div className="plot-host" ref={hostRef}>
        {/* Plot owns this node's children and nothing else; the overlay below is React's. */}
        <div className="plot-svg" ref={plotRef} />
        <div
          className="drag-surface"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={() => setHover(null)}
        >
          {scale
            ? drawn.map((band) => (
                <div
                  key={band.id}
                  className={`band band-${band.kind}`}
                  style={{
                    left: `${left(band.span.t_start)}px`,
                    width: `${Math.max(1, left(band.span.t_end) - left(band.span.t_start))}px`,
                  }}
                  title={band.title}
                />
              ))
            : null}
          {scale ? <div className="playhead" style={{ left: `${left(now)}px` }} /> : null}
          {scale && hover !== null ? (
            <div className="hoverline" style={{ left: `${left(hover)}px` }} />
          ) : null}
        </div>
      </div>
    </section>
  );
}
