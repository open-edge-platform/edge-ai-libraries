import { useGetBenchmarkTestRunByIdQuery } from "@/api/api.generated.ts";
import { Card, CardContent } from "@/components/ui/card";
import { BackButton } from "@/components/shared/BackButton";
import { useParams, useSearchParams } from "react-router";
import {
  CpuUsageChart,
  FrameRateChart,
  MemoryUtilizationChart,
} from "@/features/metrics/charts";
import { useEffect, useMemo } from "react";
import type { MetricsMessage } from "@/store/reducers/metrics.ts";
import { CONTENT_CONTAINER_CLASS } from "@/lib/utils";

export const BenchmarkRunTestDetail = () => {
  const [searchParams] = useSearchParams();
  const source = searchParams.get("source");
  const { benchmarkId, runId, testId } = useParams<{
    benchmarkId: string;
    runId: string;
    testId: string;
  }>();

  const parsedRunId = Number(runId);
  const parsedTestId = Number(testId);
  const hasValidRunId = Number.isInteger(parsedRunId);
  const hasValidTestId = Number.isInteger(parsedTestId);
  const sourceSuffix = source ? `?source=${encodeURIComponent(source)}` : "";

  const {
    data: testRunDetails,
    isLoading,
    error,
  } = useGetBenchmarkTestRunByIdQuery(
    {
      suiteSlug: benchmarkId ?? "",
      runId: parsedRunId,
      testRunId: parsedTestId,
    },
    {
      skip: !benchmarkId || !hasValidRunId || !hasValidTestId,
    },
  );

  const fpsData = useMemo(() => {
    if (!testRunDetails?.metrics) return [];
    try {
      const parsed: MetricsMessage[] = JSON.parse(testRunDetails.metrics);

      return parsed.flatMap((batch) => {
        if (!Array.isArray(batch.metrics)) {
          return [];
        }

        return batch.metrics
          .filter((metric) => metric.name === "fps")
          .map((metric) => ({
            timestamp: metric.timestamp,
            value: metric.value,
          }));
      });
    } catch {
      return [];
    }
  }, [testRunDetails?.metrics]);

  const memoryData = useMemo(() => {
    if (!testRunDetails?.metrics) return [];
    try {
      const parsed: MetricsMessage[] = JSON.parse(testRunDetails.metrics);

      return parsed.flatMap((batch) => {
        if (!Array.isArray(batch.metrics)) {
          return [];
        }

        return batch.metrics
          .filter((metric) => metric.name === "mem_used_percent")
          .map((metric) => ({
            timestamp: metric.timestamp,
            memory: metric.value,
          }));
      });
    } catch {
      return [];
    }
  }, [testRunDetails?.metrics]);

  const cpuData = useMemo(() => {
    if (!testRunDetails?.metrics) return [];
    try {
      const parsed: MetricsMessage[] = JSON.parse(testRunDetails.metrics);

      return parsed.flatMap((batch) => {
        if (!Array.isArray(batch.metrics)) {
          return [];
        }

        return batch.metrics
          .filter(
            (metric) =>
              metric.name === "cpu_usage_user" &&
              metric.labels?.cpu === "cpu-total",
          )
          .map((metric) => ({
            timestamp: metric.timestamp,
            user: metric.value,
          }));
      });
    } catch {
      return [];
    }
  }, [testRunDetails?.metrics]);

  const fpsYAxisMax = useMemo(
    () =>
      fpsData.length > 0
        ? Math.ceil(Math.max(...fpsData.map((d) => d.value)))
        : 0,
    [fpsData],
  );

  useEffect(() => {
    if (!testRunDetails) return;

    console.log("[BenchmarkRunTestDetail] loaded metrics", {
      testRunId: testRunDetails.id,
      suiteName: testRunDetails.suite.name,
      rawMetrics: testRunDetails.metrics,
      parsedMetricBatches: testRunDetails.metrics
        ? JSON.parse(testRunDetails.metrics)
        : [],
      fpsData,
      fpsYAxisMax,
      memoryData,
      cpuData,
    });
  }, [cpuData, fpsData, fpsYAxisMax, memoryData, testRunDetails]);

  if (isLoading) {
    //TODO: skeleton
    return (
      <div className={CONTENT_CONTAINER_CLASS}>
        <Card>
          <CardContent className="pt-6">
            <p className="text-muted-foreground">
              Loading benchmark test run...
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (
    !benchmarkId ||
    !hasValidRunId ||
    !hasValidTestId ||
    error ||
    !testRunDetails
  ) {
    return (
      <div className={CONTENT_CONTAINER_CLASS}>
        <Card>
          <CardContent className="pt-6">
            <p className="text-destructive">
              Failed to load benchmark test run.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className={CONTENT_CONTAINER_CLASS}>
      <div className="mb-6">
        <div className="mb-2 flex items-center gap-4">
          <BackButton
            to={`/benchmarks/${testRunDetails.suite.slug}/run/${testRunDetails.suite_run_id}${sourceSuffix}`}
          />
          <h1 className="text-3xl font-bold">
            Test #{testRunDetails.id} of {testRunDetails.suite.name}
          </h1>
        </div>
      </div>
      <div className="space-y-6">
        <FrameRateChart data={fpsData} yAxisMax={fpsYAxisMax || 1} />
        <MemoryUtilizationChart data={memoryData} />
        <CpuUsageChart data={cpuData} />
      </div>
    </div>
  );
};
