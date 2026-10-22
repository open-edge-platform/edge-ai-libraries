import { useMemo, useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { StatusBadge } from "@/components/StatusBadge";
import { TablePagination } from "@/components/TablePagination";
import { ExperimentsTable } from "@/features/benchmarks/ExperimentsTable";
import { NewExperimentDialog } from "@/features/benchmarks/NewExperimentDialog";
import { CompareBar } from "@/features/compare/CompareBar";
import { DateRangeFilter } from "@/features/compare/DateRangeFilter";
import { useRefSelection } from "@/features/compare/useRefSelection";
import { usePagination } from "@/hooks/usePagination";
import {
  useGetBenchmarkRunsQuery,
  useGetExperimentsQuery,
} from "@/api/portalApi";
import { CONTENT_CONTAINER_CLASS } from "@/lib/utils";
import { EMPTY_DATE_RANGE, isWithinDateRange } from "@/lib/dateRange";
import { formatTimestamp } from "@/lib/timeUtils";
import { formatDuration, formatMetric } from "@/lib/format";
import { Label } from "@/components/ui/label";

const ALL = "__all__";
const UNSUCCESSFUL_STATUSES = new Set(["cancelled", "failed"]);

export const Benchmarks = () => {
  const { data: runs, isLoading } = useGetBenchmarkRunsQuery(undefined, {
    pollingInterval: 15_000,
  });
  const { data: experiments } = useGetExperimentsQuery(undefined, {
    pollingInterval: 1_000,
  });
  const selection = useRefSelection();
  const [instanceFilter, setInstanceFilter] = useState(ALL);
  const [suiteFilter, setSuiteFilter] = useState(ALL);
  const [dateRange, setDateRange] = useState(EMPTY_DATE_RANGE);
  const [hideUnsuccessful, setHideUnsuccessful] = useState(true);

  const instanceOptions = useMemo(
    () => [
      ...new Map(
        (runs ?? []).map((run) => [run.instance_id, run.instance_name]),
      ),
    ],
    [runs],
  );
  const suiteOptions = useMemo(
    () => [...new Set((runs ?? []).map((run) => run.suite_slug))],
    [runs],
  );
  const experimentRefs = useMemo(
    () =>
      new Set(
        (experiments ?? []).flatMap((experiment) =>
          experiment.runs.map((run) => run.ref).filter(Boolean),
        ),
      ),
    [experiments],
  );

  const visibleRuns = (runs ?? []).filter(
    (run) =>
      !experimentRefs.has(run.ref) &&
      (instanceFilter === ALL || String(run.instance_id) === instanceFilter) &&
      (suiteFilter === ALL || run.suite_slug === suiteFilter) &&
      isWithinDateRange(run.start_time, dateRange) &&
      !(
        hideUnsuccessful && UNSUCCESSFUL_STATUSES.has(run.status.toLowerCase())
      ),
  );

  const { pageItems, controls } = usePagination(visibleRuns);

  return (
    <div className={CONTENT_CONTAINER_CLASS}>
      <h1 className="mb-2 text-3xl font-bold">Benchmarks</h1>
      <p className="mb-8 text-muted-foreground">
        Start a suite on several machines at once, or compare runs that already
        exist on the machines.
      </p>

      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Experiments</h2>
          <p className="text-sm text-muted-foreground">
            Suites launched from the portal — every machine in an experiment is
            compared together, no selection needed.
          </p>
        </div>
        <NewExperimentDialog />
      </div>
      <ExperimentsTable />

      <h2 className="mt-10 text-xl font-semibold">Other runs</h2>
      <p className="mb-4 text-sm text-muted-foreground">
        Runs started outside the portal. Select up to {selection.limit} of them
        — from the same or different machines — to compare them side by side.
      </p>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Select value={instanceFilter} onValueChange={setInstanceFilter}>
          <SelectTrigger className="w-[16rem]">
            <SelectValue placeholder="All machines" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All machines</SelectItem>
            {instanceOptions.map(([id, name]) => (
              <SelectItem key={id} value={String(id)}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={suiteFilter} onValueChange={setSuiteFilter}>
          <SelectTrigger className="w-[16rem]">
            <SelectValue placeholder="All suites" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All suites</SelectItem>
            {suiteOptions.map((slug) => (
              <SelectItem key={slug} value={slug}>
                {slug}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DateRangeFilter
          idPrefix="benchmarks"
          value={dateRange}
          onChange={setDateRange}
        />
        <div className="flex h-9 items-center gap-2">
          <Checkbox
            id="hide-unsuccessful"
            checked={hideUnsuccessful}
            onCheckedChange={(checked) => setHideUnsuccessful(checked === true)}
          />
          <Label htmlFor="hide-unsuccessful" className="font-normal">
            Hide cancelled &amp; failed
          </Label>
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <Table className="border rounded-lg">
          <TableHeader className="bg-muted">
            <TableRow>
              <TableHead className="w-[3rem]" />
              <TableHead>Machine</TableHead>
              <TableHead>Suite</TableHead>
              <TableHead>Run</TableHead>
              <TableHead>Date</TableHead>
              <TableHead className="text-right">Duration</TableHead>
              <TableHead className="text-right">Overall</TableHead>
              <TableHead className="text-right">Perf</TableHead>
              <TableHead className="text-right">Efficiency</TableHead>
              <TableHead className="text-right">Pass rate</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pageItems.map((run) => {
              const total = run.total_test_cases ?? 0;
              const passRate = total
                ? ((run.passed_test_cases ?? 0) / total) * 100
                : null;
              const checked = selection.isSelected(run.ref);

              return (
                <TableRow
                  key={run.ref}
                  data-state={checked ? "selected" : undefined}
                >
                  <TableCell>
                    <Checkbox
                      checked={checked}
                      disabled={
                        !checked && selection.selected.length >= selection.limit
                      }
                      onCheckedChange={() => selection.toggle(run.ref)}
                      aria-label={`Select run ${run.ref}`}
                    />
                  </TableCell>
                  <TableCell className="font-medium">
                    {run.instance_name}
                  </TableCell>
                  <TableCell>{run.suite_name ?? run.suite_slug}</TableCell>
                  <TableCell className="font-mono text-xs">#{run.id}</TableCell>
                  <TableCell>{formatTimestamp(run.start_time)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {run.execution_time
                      ? formatDuration(run.execution_time)
                      : "–"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium">
                    {formatMetric("score_total", run.score_total)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMetric("score_performance", run.score_performance)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMetric("score_efficiency", run.score_efficiency)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {passRate === null ? "–" : `${passRate.toFixed(0)}%`}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={run.status} />
                  </TableCell>
                </TableRow>
              );
            })}
            {visibleRuns.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={11}
                  className="text-center text-muted-foreground"
                >
                  No benchmark runs found.
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      )}

      {isLoading ? null : (
        <TablePagination idPrefix="benchmarks" {...controls} />
      )}

      <CompareBar
        count={selection.selected.length}
        limit={selection.limit}
        compareTo={selection.compareHref("/benchmarks")}
        onClear={selection.clear}
      />
      <div className="h-10" />
    </div>
  );
};
