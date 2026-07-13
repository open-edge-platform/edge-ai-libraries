import { useParams, useSearchParams } from "react-router";
import {
  useGetBenchmarkSuiteBySlugQuery,
  useGetBenchmarkSuiteRunByIdQuery,
} from "@/api/api.generated.ts";
import { Card, CardContent } from "@/components/ui/card";
import { BackButton } from "@/components/shared/BackButton";
import { useAppSelector } from "@/store/hooks";
import { selectPipelinesMap } from "@/store/reducers/pipelines";
import { useEffect, useState } from "react";
import { BenchmarkSuiteRunDetailsTable } from "@/features/benchmarks/BenchmarkSuiteRunDetailsTable.tsx";
import { BenchmarkSuiteRunDetailsSkeleton } from "@/features/benchmarks/BenchmarkSuiteRunDetailsSkeleton.tsx";
import { RunBenchmarkButton } from "@/features/benchmarks/RunBenchmarkButton";
import { BenchmarkExportButton } from "@/features/benchmarks/BenchmarkExportButton.tsx";
import { renderBenchmarkStatus } from "@/features/benchmarks/utils";
import { formatTimestamp } from "@/lib/timeUtils";

const TERMINAL_RUN_STATUSES = new Set(["passed", "failed", "cancelled"]);

export const BenchmarkRunDetail = () => {
  const { id, runId } = useParams<{ id: string; runId: string }>();
  const [searchParams] = useSearchParams();
  const source = searchParams.get("source");
  const pipelinesMap = useAppSelector(selectPipelinesMap);

  const parsedRunId = Number(runId);
  const hasValidRunId = Number.isInteger(parsedRunId);
  const [shouldPollRun, setShouldPollRun] = useState(false);

  const {
    data: benchmark,
    isLoading: isLoadingBenchmark,
    error: benchmarkLoadError,
  } = useGetBenchmarkSuiteBySlugQuery({ suiteSlug: id ?? "" }, { skip: !id });

  const {
    data: runDetails,
    isLoading: isLoadingRun,
    error: runLoadError,
  } = useGetBenchmarkSuiteRunByIdQuery(
    { suiteSlug: id ?? "", runId: parsedRunId },
    {
      skip: !id || !hasValidRunId,
      pollingInterval: shouldPollRun ? 1000 : 0,
    },
  );

  useEffect(() => {
    if (!runDetails) return;
    setShouldPollRun(!TERMINAL_RUN_STATUSES.has(runDetails.status));
  }, [runDetails]);

  const backLinkTo =
    source === "benchmark-results"
      ? "/benchmarks"
      : `/benchmarks/${id ?? ""}${source ? `?source=${source}` : ""}`;
  const isLoadingPipelines = pipelinesMap.size === 0;

  if (isLoadingBenchmark || isLoadingRun || isLoadingPipelines) {
    return <BenchmarkSuiteRunDetailsSkeleton backLinkTo={backLinkTo} />;
  }

  if (
    !id ||
    !hasValidRunId ||
    benchmarkLoadError ||
    runLoadError ||
    !benchmark ||
    !runDetails
  ) {
    return (
      <div className="container pl-16 mx-auto py-10">
        <Card>
          <CardContent className="pt-6">
            <p className="text-destructive">
              Failed to load benchmark run details.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const isActiveRun = !TERMINAL_RUN_STATUSES.has(runDetails.status);

  return (
    <div className="container pl-16 mx-auto py-10">
      <div id="benchmark-results-export">
        <div className="mb-6">
          <div className="mb-2 flex items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <BackButton to={backLinkTo} data-export-ignore />
              <h1 className="text-3xl font-bold">
                {isActiveRun
                  ? `Running ${benchmark.name} (#${runDetails.id})`
                  : `${benchmark.name} Results | ${formatTimestamp(runDetails.start_time)} (#${runDetails.id})`}
              </h1>
            </div>
            {runDetails.status === "passed" && (
              <BenchmarkExportButton
                benchmark={benchmark}
                runDetails={runDetails}
              />
            )}
          </div>
          <div className="text-muted-foreground ml-14 flex items-center gap-2">
            <span>Status:</span>
            {renderBenchmarkStatus(runDetails.status)}
          </div>
        </div>

        <div className="mt-6 mb-4 flex items-center justify-between gap-4">
          <h1 className="font-medium text-xl">Workloads</h1>
          {isActiveRun && (
            <div data-export-ignore>
              <RunBenchmarkButton suiteSlug={benchmark.slug} />
            </div>
          )}
        </div>
        <BenchmarkSuiteRunDetailsTable
          benchmark={benchmark}
          runDetails={runDetails}
          pipelinesMap={pipelinesMap}
          suiteSlug={id ?? ""}
          source={source}
        />
      </div>
    </div>
  );
};
