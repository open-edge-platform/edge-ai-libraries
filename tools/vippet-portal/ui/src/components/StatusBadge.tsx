import { Badge } from "@/components/ui/badge";

const SUCCESS = new Set(["completed", "success"]);
const FAILURE = new Set(["failed", "error"]);
const NEUTRAL = new Set([
  "cancelled",
  "skipped",
  "created",
  "queued",
  "stopped",
]);

/** Renders a ViPPET suite status or a test job state consistently. */
export const StatusBadge = ({
  status,
}: {
  status: string | null | undefined;
}) => {
  if (!status) return <span className="text-muted-foreground">–</span>;

  const normalised = status.toLowerCase();
  if (SUCCESS.has(normalised))
    return <Badge variant="success">Completed</Badge>;
  if (FAILURE.has(normalised))
    return <Badge variant="destructive">Failed</Badge>;
  if (normalised === "running")
    return (
      <span className="animate-pulse text-sm text-brand-accent">running</span>
    );
  if (NEUTRAL.has(normalised))
    return (
      <Badge variant="outline" className="capitalize">
        {normalised}
      </Badge>
    );
  return <span className="text-muted-foreground capitalize">{normalised}</span>;
};
