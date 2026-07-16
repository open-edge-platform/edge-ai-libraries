import { Badge } from "@/components/ui/badge";

export const formatBenchmarkScore = (value: number | null | undefined) => {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(2);
};

export const renderBenchmarkStatus = (status: string) => {
  if (status === "passed") {
    return <Badge variant="success">Passed</Badge>;
  }
  if (status === "created") {
    return <Badge variant="outline">Queued</Badge>;
  }
  if (status === "failed") {
    return <Badge variant="destructive">Failed</Badge>;
  }
  if (status === "running") {
    return (
      <span className="animate-pulse text-benchmark-status-running">
        running
      </span>
    );
  }
  if (status === "cancelled") {
    return <Badge variant="outline">Cancelled</Badge>;
  }
  return <span className="text-muted-foreground">{status}</span>;
};
