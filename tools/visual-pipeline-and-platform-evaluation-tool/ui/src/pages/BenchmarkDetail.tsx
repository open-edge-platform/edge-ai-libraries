import { Link, useParams, useSearchParams } from "react-router";
import {
  type BenchmarkSuiteRun,
  useGetBenchmarkSuiteBySlugQuery,
  useGetBenchmarkSuiteRunsQuery,
} from "@/api/api.generated.ts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ArrowLeft } from "lucide-react";
import { useAppSelector } from "@/store/hooks";
import { selectPipelinesMap } from "@/store/reducers/pipelines";
import { BenchmarkSuiteWorkloadsTable } from "@/features/benchmarks/BenchmarkSuiteWorkloadsTable";
import { BenchmarkSuiteResultsTable } from "@/features/benchmarks/BenchmarkSuiteResultsTable";
import { BenchmarkSuiteDetailsSkeleton } from "@/features/benchmarks/BenchmarkSuiteDetailsSkeleton";
import { RunBenchmarkButton } from "@/features/benchmarks/RunBenchmarkButton";

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

  if (isLoadingBenchmark || isLoadingPipelines) {
    return <BenchmarkSuiteDetailsSkeleton source={source} />;
  }

  if (benchmarkLoadError || !benchmark) {
    return (
      <div className="container pl-16 mx-auto py-10">
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
    <div className="container pl-16 mx-auto py-10">
      <div className="mb-6">
        <div className="flex items-center gap-4 mb-2">
          <Link
            to={source === "dashboard" ? "/" : "/benchmarks"}
            className="size-8 flex items-center justify-center hover:bg-accent dark:hover:bg-accent/50 transition-colors"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <h1 className="text-3xl font-bold">{benchmark.name}</h1>
        </div>
        <p className="text-muted-foreground ml-14">{benchmark.description}</p>
      </div>
      <div className="mb-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <h1 className="font-medium text-xl">Workloads</h1>
          <Badge variant="outline">{benchmark.workloads.length}</Badge>
        </div>
        <RunBenchmarkButton suiteSlug={benchmark.slug} />
      </div>
      <BenchmarkSuiteWorkloadsTable
        benchmark={benchmark}
        pipelinesMap={pipelinesMap}
      />
      <h1 className="font-medium text-xl mt-6 mb-4">Benchmark Results</h1>
      <BenchmarkSuiteResultsTable
        source={source}
        suiteSlug={benchmark.slug}
        suiteRuns={suiteRuns}
      />
    </div>
  );
};
