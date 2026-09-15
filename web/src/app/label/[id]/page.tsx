import { SessionView } from "./session-view";

/**
 * Next 15 made route params a Promise, so they are awaited rather than read directly.
 * The old synchronous form still type-checks — Next does not constrain a page's props —
 * so this would have failed at runtime, not at build.
 */
export default async function LabelSession({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SessionView activityId={id} />;
}
