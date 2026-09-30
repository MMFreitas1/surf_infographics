import { SessionScreen } from "./session-screen";

/**
 * N2 · Sessão — the screen the design leads with.
 *
 * `params` is a Promise and must be awaited. `tsc --noEmit` does **not** catch the old
 * synchronous form because Next does not constrain a page's props type, so this only fails
 * in a browser — which is what `pnpm run verify` exists to notice (PR #29's note in PLAN.md).
 */
export default async function SessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SessionScreen activityId={id} />;
}
