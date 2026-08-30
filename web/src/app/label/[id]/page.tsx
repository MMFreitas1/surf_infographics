import { SessionView } from "./session-view";

export default function LabelSession({ params }: { params: { id: string } }) {
  return <SessionView activityId={params.id} />;
}
