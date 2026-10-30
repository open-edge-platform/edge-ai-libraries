import { Link } from "react-router";
import { BarChart3, Trash2 } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/StatusBadge";
import {
  useDeleteTestExperimentMutation,
  useGetTestExperimentsQuery,
  type TestExperiment,
  type TestKind,
} from "@/api/portalApi";
import { formatDuration, formatMetric } from "@/lib/format";
import { formatTimestamp } from "@/lib/timeUtils";

const compareHref = (experiment: TestExperiment) => {
  const refs = experiment.runs
    .map(run => run.ref)
    .filter((ref): ref is string => Boolean(ref));
  if (refs.length < 2) return null;
  return `/tests/${experiment.kind}/compare?${refs
    .map(ref => `refs=${encodeURIComponent(ref)}`)
    .join("&")}`;
};

const settings = (experiment: TestExperiment) =>
  (experiment.kind === "density"
    ? `${experiment.fps_floor} fps floor`
    : `${experiment.streams} stream${experiment.streams === 1 ? "" : "s"}`) +
  (experiment.max_runtime ? ` · ${experiment.max_runtime}s` : "");

export const TestExperimentsTable = ({
  kind,
  metricHeader,
}: {
  kind: TestKind;
  metricHeader: string;
}) => {
  const { data: experiments, isLoading } = useGetTestExperimentsQuery(kind, {
    pollingInterval: 1_000,
  });
  const [deleteExperiment] = useDeleteTestExperimentMutation();

  if (isLoading) return <Skeleton className="h-40 w-full" />;

  return (
    <Table className="border rounded-lg">
      <TableHeader className="bg-muted">
        <TableRow>
          <TableHead>Machine</TableHead>
          <TableHead className="text-right">Duration</TableHead>
          <TableHead className="text-right">{metricHeader}</TableHead>
          <TableHead className="text-right">Per-stream FPS</TableHead>
          <TableHead>State</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {(experiments ?? []).map(experiment => {
          const href = compareHref(experiment);

          return [
            <TableRow
              key={`test-experiment-${experiment.id}`}
              className="bg-muted/40"
            >
              <TableCell colSpan={5}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="font-semibold">{experiment.label}</span>
                    <span className="text-sm text-muted-foreground">
                      {settings(experiment)} ·{" "}
                      {formatTimestamp(Date.parse(experiment.created_at))} ·{" "}
                      {experiment.runs.length} machine
                      {experiment.runs.length === 1 ? "" : "s"}
                    </span>
                    <StatusBadge status={experiment.state} />
                  </div>
                  <div className="flex items-center gap-1">
                    {href ? (
                      <Button variant="outline" size="sm" asChild>
                        <Link to={href}>
                          <BarChart3 className="h-4 w-4" />
                          Compare
                        </Link>
                      </Button>
                    ) : (
                      <Button variant="outline" size="sm" disabled>
                        <BarChart3 className="h-4 w-4" />
                        Compare
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Remove experiment ${experiment.id}`}
                      onClick={() => deleteExperiment(experiment.id)}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              </TableCell>
            </TableRow>,
            ...experiment.runs.map(run => (
              <TableRow
                key={`test-experiment-${experiment.id}-${run.instance_id}`}
              >
                <TableCell className="pl-8 font-medium">
                  {run.instance_name}
                  {run.error ? (
                    <span className="ml-2 text-sm font-normal text-destructive">
                      {run.error}
                    </span>
                  ) : null}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {run.elapsed_time ? formatDuration(run.elapsed_time) : "–"}
                </TableCell>
                <TableCell className="text-right font-medium tabular-nums">
                  {kind === "density"
                    ? formatMetric("total_streams", run.total_streams)
                    : formatMetric("total_fps", run.total_fps)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatMetric("per_stream_fps", run.per_stream_fps)}
                </TableCell>
                <TableCell>
                  <StatusBadge status={run.state} />
                </TableCell>
              </TableRow>
            )),
          ];
        })}
        {(experiments?.length ?? 0) === 0 ? (
          <TableRow>
            <TableCell
              colSpan={5}
              className="text-center text-muted-foreground"
            >
              No experiments yet — start one to run the same workload on several
              machines at once.
            </TableCell>
          </TableRow>
        ) : null}
      </TableBody>
    </Table>
  );
};
