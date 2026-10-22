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
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { StatusBadge } from "@/components/StatusBadge";
import { TablePagination } from "@/components/TablePagination";
import { NewTestDialog } from "@/features/tests/NewTestDialog";
import { TestExperimentsTable } from "@/features/tests/TestExperimentsTable";
import { CompareBar } from "@/features/compare/CompareBar";
import { DateRangeFilter } from "@/features/compare/DateRangeFilter";
import { useRefSelection } from "@/features/compare/useRefSelection";
import { usePagination } from "@/hooks/usePagination";
import {
  useGetTestExperimentsQuery,
  useGetTestJobsQuery,
  type TestKind,
} from "@/api/portalApi";
import { CONTENT_CONTAINER_CLASS } from "@/lib/utils";
import { EMPTY_DATE_RANGE, isWithinDateRange } from "@/lib/dateRange";
import { formatTimestamp } from "@/lib/timeUtils";
import { formatDuration, formatMetric } from "@/lib/format";

const ALL = "__all__";

const COPY: Record<
  TestKind,
  { title: string; description: string; metricHeader: string }
> = {
  performance: {
    title: "Performance tests",
    description:
      "Start a workload on several machines at once, or compare runs that already exist on the machines.",
    metricHeader: "Total FPS",
  },
  density: {
    title: "Density tests",
    description:
      "Start a density search on several machines at once, or compare runs that already exist on the machines.",
    metricHeader: "Max streams",
  },
};

export const TestJobsPage = ({ kind }: { kind: TestKind }) => {
  const { data: jobs, isLoading } = useGetTestJobsQuery(kind, {
    pollingInterval: 15_000,
  });
  const { data: experiments } = useGetTestExperimentsQuery(kind, {
    pollingInterval: 1_000,
  });
  const selection = useRefSelection();
  const [instanceFilter, setInstanceFilter] = useState(ALL);
  const [stateFilter, setStateFilter] = useState("COMPLETED");
  const [dateRange, setDateRange] = useState(EMPTY_DATE_RANGE);
  const [search, setSearch] = useState("");
  const copy = COPY[kind];

  const instanceOptions = useMemo(
    () => [
      ...new Map(
        (jobs ?? []).map((job) => [job.instance_id, job.instance_name]),
      ),
    ],
    [jobs],
  );
  const stateOptions = useMemo(
    () => [...new Set((jobs ?? []).map((job) => job.state))],
    [jobs],
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

  const needle = search.trim().toLowerCase();
  const visibleJobs = (jobs ?? []).filter(
    (job) =>
      !experimentRefs.has(job.ref) &&
      (instanceFilter === ALL || String(job.instance_id) === instanceFilter) &&
      (stateFilter === ALL || job.state === stateFilter) &&
      isWithinDateRange(job.start_time, dateRange) &&
      (!needle || (job.workload ?? "").toLowerCase().includes(needle)),
  );

  const { pageItems, controls } = usePagination(visibleJobs);

  return (
    <div className={CONTENT_CONTAINER_CLASS}>
      <h1 className="mb-2 text-3xl font-bold">{copy.title}</h1>
      <p className="mb-8 text-muted-foreground">{copy.description}</p>

      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Experiments</h2>
          <p className="text-sm text-muted-foreground">
            Workloads launched from the portal — every machine in an experiment
            is compared together, no selection needed.
          </p>
        </div>
        <NewTestDialog kind={kind} />
      </div>
      <TestExperimentsTable kind={kind} metricHeader={copy.metricHeader} />

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
        <Select value={stateFilter} onValueChange={setStateFilter}>
          <SelectTrigger className="w-[12rem]">
            <SelectValue placeholder="All states" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All states</SelectItem>
            {stateOptions.map((state) => (
              <SelectItem key={state} value={state}>
                {state}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          className="w-[20rem]"
          placeholder="Filter by workload…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <DateRangeFilter
          idPrefix={kind}
          value={dateRange}
          onChange={setDateRange}
        />
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <Table className="border rounded-lg">
          <TableHeader className="bg-muted">
            <TableRow>
              <TableHead className="w-[3rem]" />
              <TableHead>Machine</TableHead>
              <TableHead>Workload</TableHead>
              <TableHead>Date</TableHead>
              <TableHead className="text-right">Duration</TableHead>
              <TableHead className="text-right">{copy.metricHeader}</TableHead>
              <TableHead className="text-right">Per-stream FPS</TableHead>
              <TableHead>State</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pageItems.map((job) => {
              const checked = selection.isSelected(job.ref);
              const headlineMetric =
                kind === "density"
                  ? formatMetric("total_streams", job.total_streams)
                  : formatMetric("total_fps", job.total_fps);

              return (
                <TableRow
                  key={job.ref}
                  data-state={checked ? "selected" : undefined}
                >
                  <TableCell>
                    <Checkbox
                      checked={checked}
                      disabled={
                        !checked && selection.selected.length >= selection.limit
                      }
                      onCheckedChange={() => selection.toggle(job.ref)}
                      aria-label={`Select job ${job.id}`}
                    />
                  </TableCell>
                  <TableCell className="font-medium">
                    {job.instance_name}
                  </TableCell>
                  <TableCell className="max-w-[24rem] truncate">
                    {job.workload ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span>{job.workload}</span>
                        </TooltipTrigger>
                        <TooltipContent>{job.workload}</TooltipContent>
                      </Tooltip>
                    ) : (
                      <span className="text-muted-foreground">
                        {job.details[0] ?? "–"}
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    {job.start_time ? formatTimestamp(job.start_time) : "–"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {job.elapsed_time ? formatDuration(job.elapsed_time) : "–"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium">
                    {headlineMetric}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMetric("per_stream_fps", job.per_stream_fps)}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={job.state} />
                  </TableCell>
                </TableRow>
              );
            })}
            {visibleJobs.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={8}
                  className="text-center text-muted-foreground"
                >
                  No {kind} tests found.
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      )}

      {isLoading ? null : <TablePagination idPrefix={kind} {...controls} />}

      <CompareBar
        count={selection.selected.length}
        limit={selection.limit}
        compareTo={selection.compareHref(`/tests/${kind}`)}
        onClear={selection.clear}
      />
      <div className="h-10" />
    </div>
  );
};
