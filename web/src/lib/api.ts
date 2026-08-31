/**
 * The API client. Every response is parsed through its Zod schema before the UI sees it.
 *
 * The parse is not ceremony. These schemas mirror `api/src/surf/models.py`, and a field that
 * quietly changes shape on the server would otherwise surface as a blank chart or a
 * mislabelled second rather than as an error. Parsing here turns that into a message in
 * `/diagnostics/errors`, where API and UI failures already sit together (ADR-0007).
 */
import type { z } from "zod";
import { reportError } from "@/lib/report-error";
import {
  ActivitySummary,
  LabelPass,
  type PassKind,
  SessionCandidates,
  SessionTrack,
  StoredLabel,
} from "@/lib/schema";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    });
  } catch {
    const message = `cannot reach the API at ${API_BASE}. Is it running? (make api)`;
    void reportError({ message, kind: "ApiUnreachable", context: { path } });
    throw new ApiError(message, 0);
  }

  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    const message =
      typeof detail?.detail === "string" ? detail.detail : `${response.status} on ${path}`;
    if (response.status >= 500) {
      void reportError({ message, kind: "ApiError", context: { path, status: response.status } });
    }
    throw new ApiError(message, response.status);
  }

  const parsed = schema.safeParse(await response.json());
  if (!parsed.success) {
    const message = `the API's response for ${path} does not match the contract`;
    void reportError({
      message,
      kind: "ContractDrift",
      context: { path, issues: parsed.error.issues.slice(0, 5) },
    });
    throw new ApiError(message, response.status);
  }
  return parsed.data;
}

export const listActivities = () => request("/activities", ActivitySummary.array());

export const getTrack = (id: string) => request(`/activities/${id}/track`, SessionTrack);

export const getCandidates = (id: string) =>
  request(`/activities/${id}/candidates`, SessionCandidates);

export const getLabels = (id: string, current = false) =>
  request(`/activities/${id}/labels${current ? "?current=true" : ""}`, StoredLabel.array());

export const getPasses = (id: string) =>
  request(`/activities/${id}/label-passes`, LabelPass.array());

/** What the UI is allowed to send. `verified` is required on purpose — see `LabelCreate`. */
export interface NewLabel {
  t_start: number;
  t_end: number;
  is_wave: boolean;
  verified: boolean;
  source?: "human" | "human_assisted";
  direction?: "left" | "right" | "straight" | "unknown";
  note?: string;
  supersedes?: string | null;
}

export const postLabel = (id: string, label: NewLabel) =>
  request(`/activities/${id}/labels`, StoredLabel, {
    method: "POST",
    body: JSON.stringify(label),
  });

export const completePass = (id: string, kind: PassKind) =>
  request(`/activities/${id}/label-passes`, LabelPass, {
    method: "POST",
    body: JSON.stringify({ kind }),
  });
