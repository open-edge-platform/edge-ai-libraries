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
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/StatusBadge";
import {
  useDeleteExperimentMutation,
  useGetExperimentsQuery,
  type Experiment,
} from "@/api/portalApi";
import { formatMetric } from "@/lib/format";
import { formatElapsedTimeMillis, formatTimestamp } from "@/lib/timeUtils";

const compareHref = (experiment: Experiment) => {
  const refs = experiment.runs
    .map((run) => run.ref)
    .filter((ref): ref is string => Boolean(ref));
  if (refs.length < 2) return null;
  return `/benchmarks/compare?${refs
    .map((ref) => `refs=${encodeURIComponent(ref)}`)
    .join("&")}`;
};

export const ExperimentsTable = () => {
  const { data: experiments, isLoading } = useGetExperimentsQuery(undefined, {
    pollingInterval: 1_000,
  });
  const [deleteExperiment] = useDeleteExperimentMutation();

  if (isLoading) return <Skeleton className="h-40 w-full" />;

  return (
    <Table className="border rounded-lg">
      <TableHeader className="bg-muted">
        <TableRow>
          <TableHead>Machine</TableHead>
          <TableHead className="w-[14rem]">Progress</TableHead>
          <TableHead className="text-right">Duration</TableHead>
          <TableHead className="text-right">Overall</TableHead>
          <TableHead className="text-right">Perf</TableHead>
          <TableHead className="text-right">Efficiency</TableHead>
          <TableHead>State</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {(experiments ?? []).map((experiment) => {
          const href = compareHref(experiment);

          return [
            <TableRow
              key={`experiment-${experiment.id}`}
              className="bg-muted/40"
            >
              <TableCell colSpan={7}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="font-semibold">
                      {experiment.suite_name ?? experiment.suite_slug}
                    </span>
                    <span className="text-sm text-muted-foreground">
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
            ...experiment.runs.map((run) => {
              const total = run.total_test_cases ?? 0;
              const done = run.completed_test_cases ?? 0;
              const percent = total ? (done / total) * 100 : 0;

              return (
                <TableRow
                  key={`experiment-${experiment.id}-${run.instance_id}`}
                >
                  <TableCell className="pl-8 font-medium">
                    {run.instance_name}
                  </TableCell>
                  <TableCell>
                    {run.error ? (
                      <span className="text-sm text-destructive">
                        {run.error}
                      </span>
                    ) : total ? (
                      <div className="flex items-center gap-2">
                        <Progress value={percent} className="w-28" />
                        <span className="text-xs tabular-nums text-muted-foreground">
                          {done}/{total}
                        </span>
                      </div>
                    ) : (
                      <span className="text-muted-foreground">–</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {run.elapsed_time
                      ? formatElapsedTimeMillis(run.elapsed_time)
                      : "–"}
                  </TableCell>
                  <TableCell className="text-right font-medium tabular-nums">
                    {formatMetric("score_total", run.score_total)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMetric("score_performance", run.score_performance)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMetric("score_efficiency", run.score_efficiency)}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={run.state} />
                  </TableCell>
                </TableRow>
              );
            }),
          ];
        })}
        {(experiments?.length ?? 0) === 0 ? (
          <TableRow>
            <TableCell
              colSpan={7}
              className="text-center text-muted-foreground"
            >
              No experiments yet — start one to run a suite on several machines
              at once.
            </TableCell>
          </TableRow>
        ) : null}
      </TableBody>
    </Table>
  );
};
