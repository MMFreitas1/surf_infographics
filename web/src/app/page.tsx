"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, listActivities } from "@/lib/api";
import type { ActivitySummary } from "@/lib/schema";

/**
 * The sessions that have been ingested.
 *
 * Coverage and blind time are on the row rather than buried in the session, because they
 * set expectations before anyone starts labelling: a session the watch saw half of is a
 * different job from one it saw nearly all of, and it is better to know that first.
 */
export default function Home() {
  const [rows, setRows] = useState<ActivitySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listActivities()
      .then(setRows)
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : String(cause)));
  }, []);

  return (
    <main className="sessions">
      <h1>Surf Infographics</h1>
      {error ? <p className="error">{error}</p> : null}
      {rows === null && !error ? <p>loading sessions…</p> : null}

      {rows?.length === 0 ? (
        <p className="muted">
          No sessions yet. Ingest one:{" "}
          <code>curl --data-binary @session.fit localhost:8000/activities</code>
        </p>
      ) : null}

      <ul className="session-list">
        {rows?.map((row) => (
          <li key={row.activity_id}>
            <Link href={`/label/${row.activity_id}`}>
              <strong>{new Date(row.start_time * 1000).toLocaleString()}</strong>
              <span className="muted">
                {row.sport} · {Math.round(row.duration_s / 60)} min · {row.fidelity}
              </span>
              <span className={row.position_coverage < 0.5 ? "coverage warn" : "coverage"}>
                {Math.round(row.position_coverage * 100)}% measured ·{" "}
                {Math.round(row.blind_seconds / 60)} min blind
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
