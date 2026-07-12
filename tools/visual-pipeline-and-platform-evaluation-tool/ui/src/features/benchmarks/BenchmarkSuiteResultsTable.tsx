import type { BenchmarkSuiteRun } from "@/api/api.generated.ts";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatElapsedTimeMillis, formatTimestamp } from "@/lib/timeUtils";
import { Loader2, MoreVertical } from "lucide-react";
import { Link } from "react-router";
import {
  formatBenchmarkScore,
  renderBenchmarkStatus,
} from "@/features/benchmarks/utils";

type BenchmarkSuiteResultsTableProps = {
  source?: string | null;
  suiteSlug: string;
  suiteName?: string;
  suiteRuns: BenchmarkSuiteRun[];
  showNameColumn?: boolean;
};

export const BenchmarkSuiteResultsTable = ({
  source,
  suiteSlug,
  suiteName,
  suiteRuns,
  showNameColumn = false,
}: BenchmarkSuiteResultsTableProps) => {
  const sourceSuffix = source ? `?source=${encodeURIComponent(source)}` : "";
  const emptyStateColSpan = showNameColumn ? 10 : 9;

  return (
    <Table className="border rounded-lg">
      <TableHeader className="bg-muted">
        <TableRow>
          <TableHead className="w-max"></TableHead>
          {showNameColumn ? (
            <TableHead className="w-max">Name</TableHead>
          ) : null}
          <TableHead className="w-max">Date</TableHead>
          <TableHead className="w-max">Duration</TableHead>
          <TableHead className="w-max">Overall score</TableHead>
          <TableHead className="w-max">Performance score</TableHead>
          <TableHead className="w-max">Efficiency score</TableHead>
          <TableHead className="w-max">Pass rate</TableHead>
          <TableHead className="w-[3.125rem]">Status</TableHead>
          <TableHead className="w-[3.5rem]"></TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {suiteRuns.length > 0 ? (
          [...suiteRuns]
            .sort((a, b) => b.start_time - a.start_time)
            .map((run) => {
              const totalTests = run.total_test_cases || 0;
              const passedTests = run.passed_test_cases || 0;
              const passRate =
                totalTests > 0 ? (passedTests / totalTests) * 100 : 0;

              return (
                <TableRow key={run.id}>
                  <TableCell className="font-mono text-center text-xs">
                    #{run.id}
                  </TableCell>
                  {showNameColumn ? (
                    <TableCell>{suiteName ?? "-"}</TableCell>
                  ) : null}
                  <TableCell>{formatTimestamp(run.start_time)}</TableCell>
                  <TableCell>
                    {formatElapsedTimeMillis(run.execution_time ?? 0)}
                  </TableCell>
                  <TableCell>
                    {run.status === "running" ? (
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    ) : (
                      formatBenchmarkScore(run.score_total)
                    )}
                  </TableCell>
                  <TableCell>
                    {run.status === "running" ? (
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    ) : (
                      formatBenchmarkScore(run.score_performance)
                    )}
                  </TableCell>
                  <TableCell>
                    {run.status === "running" ? (
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    ) : (
                      formatBenchmarkScore(run.score_efficiency)
                    )}
                  </TableCell>
                  <TableCell>
                    {passRate.toFixed(1)}% ({run.passed_test_cases}/
                    {run.total_test_cases})
                  </TableCell>
                  <TableCell>{renderBenchmarkStatus(run.status)}</TableCell>
                  <TableCell className="text-center">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          aria-label={`Open actions for run ${run.id}`}
                        >
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="start">
                        <DropdownMenuItem asChild>
                          <Link
                            to={`/benchmarks/${suiteSlug}/run/${run.id}${sourceSuffix}`}
                          >
                            View details
                          </Link>
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              );
            })
        ) : (
          <TableRow>
            <TableCell
              colSpan={emptyStateColSpan}
              className="text-center text-muted-foreground py-6"
            >
              No benchmark results yet.
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
};
