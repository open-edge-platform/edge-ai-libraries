import type {
  BenchmarkSuite,
  BenchmarkSuiteRunDetails,
  Pipeline,
} from "@/api/api.generated.ts";
import { useStopPerformanceTestJobMutation } from "@/api/api.generated.ts";
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
import { formatElapsedTimeMillis } from "@/lib/timeUtils";
import { ChevronDown, ChevronRight, Loader2, MoreVertical } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import {
  formatBenchmarkScore,
  renderBenchmarkStatus,
} from "@/features/benchmarks/utils";

const THUMBNAIL_PLACEHOLDER = "/src/assets/thumbnail_placeholder.png";

type TestCaseColumn = {
  key: string;
  width: number;
  exportIgnore?: boolean;
};

const TEST_CASE_COLUMNS: TestCaseColumn[] = [
  { key: "variant", width: 100 },
  { key: "streams", width: 80 },
  { key: "duration", width: 100 },
  { key: "total-fps", width: 100 },
  { key: "per-stream-fps", width: 120 },
  { key: "cpu", width: 80 },
  { key: "gpu", width: 80 },
  { key: "npu", width: 80 },
  { key: "media", width: 80 },
  { key: "memory", width: 90 },
  { key: "power", width: 90 },
  { key: "status", width: 50 },
  { key: "actions", width: 20, exportIgnore: true },
];

const TestCaseColGroup = () => (
  <colgroup>
    {TEST_CASE_COLUMNS.map((column) => (
      <col
        key={column.key}
        style={{ width: column.width }}
        data-export-ignore={column.exportIgnore ? true : undefined}
      />
    ))}
  </colgroup>
);

type BenchmarkSuiteResultDetailsTableProps = {
  benchmark: BenchmarkSuite;
  runDetails: BenchmarkSuiteRunDetails;
  pipelinesMap: Map<string, Pipeline>;
  suiteSlug: string;
  source?: string | null;
};

export const BenchmarkSuiteResultDetailsTable = ({
  benchmark,
  runDetails,
  pipelinesMap,
  suiteSlug,
  source,
}: BenchmarkSuiteResultDetailsTableProps) => {
  const navigate = useNavigate();
  const [stopPerformanceTestJob] = useStopPerformanceTestJobMutation();
  const [expandedRows, setExpandedRows] = useState<Set<number>>(
    () =>
      new Set(runDetails.workload_runs.map((workloadRun) => workloadRun.id)),
  );

  const toggleExpanded = (rowId: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(rowId)) {
        next.delete(rowId);
      } else {
        next.add(rowId);
      }
      return next;
    });
  };

  const handleCancelTest = async (jobId: string) => {
    try {
      await stopPerformanceTestJob({ jobId }).unwrap();
    } catch (error) {
      console.error("Failed to cancel test:", error);
    }
  };

  const sourceSuffix = source ? `?source=${encodeURIComponent(source)}` : "";

  return (
    <Table className="border rounded-lg">
      <TableHeader className="bg-muted">
        <TableRow>
          <TableHead className="w-10"></TableHead>
          <TableHead className="w-32"></TableHead>
          <TableHead className="w-max">Pipeline Name</TableHead>
          <TableHead className="w-max">Overall score</TableHead>
          <TableHead className="w-max">Performance score</TableHead>
          <TableHead className="w-max">Efficiency score</TableHead>
          <TableHead className="w-max">Duration</TableHead>
          <TableHead className="w-max">Pass rate</TableHead>
          <TableHead className="w-max">Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {runDetails.workload_runs.length > 0 ? (
          runDetails.workload_runs.map((workloadRun) => {
            const total = workloadRun.total_test_cases || 0;
            const passed = workloadRun.passed_test_cases || 0;
            const passRate = total > 0 ? (passed / total) * 100 : 0;
            const workload = benchmark.workloads.find(
              (w) => w.id === workloadRun.workload_id,
            );
            const pipeline = workload
              ? pipelinesMap.get(workload.pipeline_id)
              : undefined;
            const pipelineName =
              pipeline?.name ??
              workload?.pipeline_id ??
              `Workload #${workloadRun.workload_id}`;
            const pipelineImage = pipeline?.thumbnail ?? THUMBNAIL_PLACEHOLDER;
            const isExpanded = expandedRows.has(workloadRun.id);

            return [
              <TableRow key={`summary-${workloadRun.id}`}>
                <TableCell>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => toggleExpanded(workloadRun.id)}
                    aria-label={`${isExpanded ? "Collapse" : "Expand"} workload ${workloadRun.id}`}
                  >
                    {isExpanded ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                  </Button>
                </TableCell>
                <TableCell>
                  <img
                    src={pipelineImage}
                    alt={pipelineName}
                    className="w-32 h-16 object-cover"
                  />
                </TableCell>
                <TableCell className="font-medium whitespace-nowrap">
                  {pipelineName}
                </TableCell>
                <TableCell>
                  {workloadRun.status === "running" ? (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  ) : (
                    formatBenchmarkScore(workloadRun.score_total)
                  )}
                </TableCell>
                <TableCell>
                  {workloadRun.status === "running" ? (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  ) : (
                    formatBenchmarkScore(workloadRun.score_performance)
                  )}
                </TableCell>
                <TableCell>
                  {workloadRun.status === "running" ? (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  ) : (
                    formatBenchmarkScore(workloadRun.score_efficiency)
                  )}
                </TableCell>
                <TableCell>
                  {formatElapsedTimeMillis(workloadRun.execution_time ?? 0)}
                </TableCell>
                <TableCell>
                  {passRate.toFixed(1)}% ({passed}/{total})
                </TableCell>
                <TableCell>
                  {renderBenchmarkStatus(workloadRun.status)}
                </TableCell>
              </TableRow>,
              isExpanded ? (
                <TableRow key={`details-${workloadRun.id}`}>
                  <TableCell colSpan={9} className="bg-muted/25 px-12">
                    <Table>
                      <TestCaseColGroup />
                      <TableHeader>
                        <TableRow>
                          <TableHead>Variant</TableHead>
                          <TableHead>Streams</TableHead>
                          <TableHead>Duration</TableHead>
                          <TableHead>Total FPS</TableHead>
                          <TableHead>Per-stream FPS</TableHead>
                          <TableHead>CPU</TableHead>
                          <TableHead>GPU</TableHead>
                          <TableHead>NPU</TableHead>
                          <TableHead>Media</TableHead>
                          <TableHead>Memory</TableHead>
                          <TableHead>Power</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead data-export-ignore></TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {workloadRun.test_case_runs.length > 0 ? (
                          workloadRun.test_case_runs.map((testCaseRun) => {
                            const variantName =
                              pipeline?.variants.find(
                                (variant) =>
                                  variant.id === testCaseRun.variant_id,
                              )?.name ?? testCaseRun.variant_id;

                            return (
                              <TableRow key={testCaseRun.id}>
                                <TableCell>{variantName}</TableCell>
                                <TableCell>{testCaseRun.streams}</TableCell>
                                <TableCell>
                                  {formatElapsedTimeMillis(
                                    testCaseRun.execution_time ?? 0,
                                  )}
                                </TableCell>
                                <TableCell>
                                  {testCaseRun.status === "running" ? (
                                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                                  ) : typeof testCaseRun.total_fps ===
                                    "number" ? (
                                    testCaseRun.total_fps.toFixed(2)
                                  ) : (
                                    "-"
                                  )}
                                </TableCell>
                                <TableCell>
                                  {testCaseRun.status === "running" ? (
                                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                                  ) : typeof testCaseRun.per_stream_fps ===
                                    "number" ? (
                                    testCaseRun.per_stream_fps.toFixed(2)
                                  ) : (
                                    "-"
                                  )}
                                </TableCell>
                                <TableCell>
                                  {testCaseRun.status === "running" ? (
                                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                                  ) : typeof testCaseRun.cpu_usage ===
                                    "number" ? (
                                    `${testCaseRun.cpu_usage.toFixed(1)}%`
                                  ) : (
                                    "-"
                                  )}
                                </TableCell>
                                <TableCell>
                                  {testCaseRun.status === "running" ? (
                                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                                  ) : typeof testCaseRun.gpu_usage ===
                                    "number" ? (
                                    `${testCaseRun.gpu_usage.toFixed(1)}%`
                                  ) : (
                                    "-"
                                  )}
                                </TableCell>
                                <TableCell>
                                  {testCaseRun.status === "running" ? (
                                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                                  ) : (
                                    "-"
                                  )}
                                </TableCell>
                                <TableCell>
                                  {testCaseRun.status === "running" ? (
                                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                                  ) : (
                                    "-"
                                  )}
                                </TableCell>
                                <TableCell>
                                  {testCaseRun.status === "running" ? (
                                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                                  ) : typeof testCaseRun.memory_usage ===
                                    "number" ? (
                                    `${testCaseRun.memory_usage.toFixed(1)}%`
                                  ) : (
                                    "-"
                                  )}
                                </TableCell>
                                <TableCell>
                                  {testCaseRun.status === "running" ? (
                                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                                  ) : typeof testCaseRun.power_usage ===
                                    "number" ? (
                                    `${testCaseRun.power_usage.toFixed(1)} W`
                                  ) : (
                                    "-"
                                  )}
                                </TableCell>
                                <TableCell>
                                  {renderBenchmarkStatus(testCaseRun.status)}
                                </TableCell>
                                <TableCell
                                  className="text-center"
                                  data-export-ignore
                                >
                                  <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                      <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        className="h-7 w-7"
                                        aria-label={`Open actions for test case ${testCaseRun.id}`}
                                      >
                                        <MoreVertical className="h-4 w-4" />
                                      </Button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="start">
                                      <DropdownMenuItem
                                        onClick={() =>
                                          navigate(
                                            `/benchmarks/${suiteSlug}/run/${runDetails.id}/test/${testCaseRun.id}${sourceSuffix}`,
                                          )
                                        }
                                      >
                                        View details
                                      </DropdownMenuItem>
                                      {testCaseRun.status === "running" && (
                                        <DropdownMenuItem
                                          onClick={() =>
                                            handleCancelTest(testCaseRun.job_id)
                                          }
                                        >
                                          Cancel test
                                        </DropdownMenuItem>
                                      )}
                                    </DropdownMenuContent>
                                  </DropdownMenu>
                                </TableCell>
                              </TableRow>
                            );
                          })
                        ) : (
                          <TableRow>
                            <TableCell
                              colSpan={13}
                              className="text-center text-muted-foreground py-4"
                            >
                              No test cases found.
                            </TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </TableCell>
                </TableRow>
              ) : null,
            ];
          })
        ) : (
          <TableRow>
            <TableCell
              colSpan={9}
              className="text-center text-muted-foreground py-6"
            >
              No workload runs found.
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
};
