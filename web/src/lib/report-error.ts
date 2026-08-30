/**
 * Ship browser errors to the API so they land in the same place as server errors.
 *
 * Front-end failures are otherwise invisible outside whoever happens to have devtools
 * open. Routing them to `/diagnostics/client-error` makes them readable over HTTP
 * (ADR-0007). Reporting is strictly best-effort: it must never throw, and must never
 * trigger another error, or a single failure becomes an error loop.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export interface ErrorReport {
  message: string;
  kind?: string;
  stack?: string;
  url?: string;
  context?: Record<string, unknown>;
}

export async function reportError(report: ErrorReport): Promise<void> {
  try {
    await fetch(`${API_BASE}/diagnostics/client-error`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: report.message,
        kind: report.kind ?? "ClientError",
        stack: report.stack ?? "",
        url: report.url ?? (typeof window === "undefined" ? "" : window.location.href),
        context: report.context ?? {},
      }),
      keepalive: true,
    });
  } catch {
    // The diagnostics channel being down must never take the UI with it.
  }
}
