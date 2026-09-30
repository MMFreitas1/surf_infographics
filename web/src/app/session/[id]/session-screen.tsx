"use client";

/**
 * The Session screen's body.
 *
 * What this PR fills: the hero count, the aerobic panel and device confidence — everything
 * the pipeline can answer today. The track map, the four chart cards and the wave profiles
 * are PR 2 and PR 3; sea state and the model's prose wait on Phases 8 and 11 and render
 * their designed absence in the meantime.
 *
 * Four requests rather than one composite endpoint, because they are four genuinely
 * different questions and the existing routes already answer them. Nothing here blocks on
 * the slowest: a panel whose request failed says so and the rest of the screen stands.
 */
import { useEffect, useState } from "react";
import { ApiError, getActivity, getAudit, getCleaning, getWaves } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Activity, AuditReport, CleanReport, SessionVerdict } from "@/lib/schema";
import { MethodBanner } from "../../_ui/method-banner";
import { AerobicPanel, DeviceConfidence, HeroCount, Unavailable } from "../../_ui/panels";
import { SectionHeader, Shell } from "../../_ui/shell";

interface Loaded {
  activity: Activity;
  waves: SessionVerdict;
  cleaning: CleanReport;
  audit: AuditReport;
}

/** Mean and max heart rate over the seconds the audit calls session. */
function heartRate(activity: Activity, audit: AuditReport) {
  const during = activity.samples.filter(
    (s) => s.t >= audit.surfing_t_start && s.t < audit.surfing_t_end && s.hr_bpm !== null,
  );
  const beats = during.map((s) => s.hr_bpm as number);
  if (beats.length === 0) return { meanBpm: null, maxBpm: null };
  return {
    meanBpm: Math.round(beats.reduce((a, b) => a + b, 0) / beats.length),
    maxBpm: Math.max(...beats),
  };
}

export function SessionScreen({ activityId }: { activityId: string }) {
  const t = useT();
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([
      getActivity(activityId),
      getWaves(activityId),
      getCleaning(activityId),
      getAudit(activityId),
    ])
      .then(([activity, waves, cleaning, audit]) => {
        if (live) setData({ activity, waves, cleaning, audit });
      })
      .catch((cause) => {
        if (live) setError(cause instanceof ApiError ? cause.message : String(cause));
      });
    return () => {
      live = false;
    };
  }, [activityId]);

  // The spot is not derived from coordinates: this repo is public and the session's position
  // is exactly what must not leak into a committed string. Phase 6 will name it from the
  // coastline lookup; until then the device stands in for it.
  const spot = data?.activity.device || "—";
  const samples = data ? String(data.activity.samples.length) : "—";

  if (error !== null) {
    return (
      <Shell active="session" spot={spot} samples={samples}>
        <p className="error">{t("state.error")}</p>
        <p className="muted">{error}</p>
      </Shell>
    );
  }

  if (data === null) {
    return (
      <Shell active="session" spot={spot} samples={samples}>
        <p className="muted">{t("state.loading")}</p>
      </Shell>
    );
  }

  const { meanBpm, maxBpm } = heartRate(data.activity, data.audit);

  return (
    <Shell active="session" spot={spot} samples={samples} sessionHref={`/session/${activityId}`}>
      <MethodBanner />
      <HeroCount verdict={data.waves} />

      <SectionHeader label="section.session" />
      <div className="panel-grid">
        <AerobicPanel meanBpm={meanBpm} maxBpm={maxBpm} durationS={data.audit.surfing_s} />
        <Unavailable title="quality.title" message="quality.unavailable" />
      </div>

      <SectionHeader label="section.conditions" />
      <div className="panel-grid">
        <Unavailable title="seaState.title" message="seaState.unavailable" />
      </div>

      <SectionHeader label="section.confidence" />
      <div className="panel-grid">
        <DeviceConfidence
          cleaning={data.cleaning}
          audit={data.audit}
          blindWindows={data.activity.blind_windows.length}
        />
      </div>
    </Shell>
  );
}
