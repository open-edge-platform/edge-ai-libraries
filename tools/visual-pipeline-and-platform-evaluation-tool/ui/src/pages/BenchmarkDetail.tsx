import { useParams, useSearchParams } from "react-router";
import {
  type BenchmarkSuiteRun,
  useGetBenchmarkSuiteBySlugQuery,
  useGetBenchmarkSuiteRunsQuery,
} from "@/api/api.generated.ts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { BackButton } from "@/components/shared/BackButton";
import { useAppSelector } from "@/store/hooks";
import { selectPipelinesMap } from "@/store/reducers/pipelines";
import { BenchmarkSuiteWorkloadsTable } from "@/features/benchmarks/BenchmarkSuiteWorkloadsTable";
import { BenchmarkSuiteRunsTable } from "@/features/benchmarks/BenchmarkSuiteRunsTable.tsx";
import { BenchmarkSuiteDetailsSkeleton } from "@/features/benchmarks/BenchmarkSuiteDetailsSkeleton";
import { RunBenchmarkButton } from "@/features/benchmarks/RunBenchmarkButton";
import { PipelineModelsRequiredDialog } from "@/features/models/PipelineModelsRequiredDialog.tsx";
import { extractModelNamesFromNodes } from "@/features/models/modelNames.ts";
import { useRequiredModelsStatus } from "@/features/models/useRequiredModelsStatus.ts";
import { CONTENT_CONTAINER_CLASS } from "@/lib/utils";
import { useMemo } from "react";

export const BenchmarkDetail = () => {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const source = searchParams.get("source");
  const pipelinesMap = useAppSelector(selectPipelinesMap);

  const {
    data: benchmark,
    isLoading: isLoadingBenchmark,
    error: benchmarkLoadError,
  } = useGetBenchmarkSuiteBySlugQuery({ suiteSlug: id ?? "" }, { skip: !id });

  const { data: benchmarkRuns } = useGetBenchmarkSuiteRunsQuery(
    { suiteSlug: id ?? "" },
    {
      skip: !id,
      pollingInterval: 1000,
    },
  );
  const suiteRuns: BenchmarkSuiteRun[] = benchmarkRuns ?? [];

  const isLoadingPipelines = pipelinesMap.size === 0;

  const requiredModels = useMemo(
    () =>
      (benchmark?.workloads ?? []).flatMap((workload) => {
        const pipeline = pipelinesMap.get(workload.pipeline_id);
        const firstVariantId = workload.variants.split(",")[0]?.trim();
        const firstVariant = firstVariantId
          ? pipeline?.variants.find((variant) => variant.id === firstVariantId)
          : undefined;

        return extractModelNamesFromNodes(firstVariant?.pipeline_graph?.nodes);
      }),
    [benchmark, pipelinesMap],
  );

  const {
    modelStatuses,
    missingModels,
    isDialogOpen,
    setIsDialogOpen,
    refresh: refreshRequiredModels,
  } = useRequiredModelsStatus(requiredModels, {
    skip: !benchmark || isLoadingPipelines,
    errorMessage: "Failed to check models used in benchmark workloads",
  });

  const missingRequiredModels = useMemo(
    () => missingModels.map((item) => item.model),
    [missingModels],
  );

  if (isLoadingBenchmark || isLoadingPipelines) {
    return <BenchmarkSuiteDetailsSkeleton source={source} />;
  }

  if (benchmarkLoadError || !benchmark) {
    return (
      <div className={CONTENT_CONTAINER_CLASS}>
        <Card>
          <CardContent className="pt-6">
            <p className="text-destructive">
              Failed to load benchmark details.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }
  return (
    <div className={CONTENT_CONTAINER_CLASS}>
      <div className="mb-6">
        <div className="flex items-center gap-4 mb-2">
          <BackButton to={source === "dashboard" ? "/" : "/benchmarks"} />
          <h1 className="text-3xl font-bold">{benchmark.name}</h1>
        </div>
        <p className="text-muted-foreground ml-14">{benchmark.description}</p>
      </div>
      <div className="mb-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <h1 className="font-medium text-xl">Workloads</h1>
          <Badge variant="outline">{benchmark.workloads.length}</Badge>
        </div>
        <RunBenchmarkButton
          suiteSlug={benchmark.slug}
          missingRequiredModels={missingRequiredModels}
        />
      </div>
      <BenchmarkSuiteWorkloadsTable
        benchmark={benchmark}
        pipelinesMap={pipelinesMap}
      />
      <h1 className="font-medium text-xl mt-6 mb-4">Benchmark Results</h1>
      <BenchmarkSuiteRunsTable suiteRuns={suiteRuns} source={source} />
      <div className="h-10" />
      <PipelineModelsRequiredDialog
        open={isDialogOpen}
        onOpenChange={setIsDialogOpen}
        models={modelStatuses}
        onModelsChanged={refreshRequiredModels}
        description="One or more models used by this benchmark's workloads are not installed."
      />
    </div>
  );
};
