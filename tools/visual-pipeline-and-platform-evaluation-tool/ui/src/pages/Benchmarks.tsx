import {
  useGetAllBenchmarkRunsQuery,
  useGetBenchmarksQuery,
} from "@/api/api.generated";
import { Card, CardContent } from "@/components/ui/card";
import { BenchmarkCards } from "@/features/benchmarks/BenchmarkCards";
import { BenchmarkSuiteRunsTable } from "@/features/benchmarks/BenchmarkSuiteRunsTable.tsx";
import { BenchmarkSuiteRunsTableSkeleton } from "@/features/benchmarks/BenchmarkSuiteRunsTableSkeleton.tsx";
import { PipelineCardsLoader } from "@/features/pipelines/PipelineCardsLoader";

export const Benchmarks = () => {
  const { data: benchmarks, isLoading, error } = useGetBenchmarksQuery();
  const {
    data: allSuiteRuns,
    isLoading: isLoadingRuns,
    error: allRunsError,
  } = useGetAllBenchmarkRunsQuery(undefined, { pollingInterval: 1000 });
  const isLoadingPage = isLoading || isLoadingRuns;

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-4">
        {isLoadingPage ? (
          <>
            <PipelineCardsLoader count={5} />
            <div className="mt-8">
              <h2 className="mb-4 text-xl font-medium">Benchmark Results</h2>
              <BenchmarkSuiteRunsTableSkeleton showNameColumn />
            </div>
          </>
        ) : error ? (
          <Card>
            <CardContent className="pt-6">
              <p className="text-destructive text-center">
                Failed to load benchmarks. Please try again later.
              </p>
            </CardContent>
          </Card>
        ) : !benchmarks || benchmarks.length === 0 ? (
          <Card>
            <CardContent className="pt-6">
              <p className="text-muted-foreground text-center">
                No benchmarks available.
              </p>
            </CardContent>
          </Card>
        ) : (
          <>
            <BenchmarkCards
              benchmarks={benchmarks}
              source="benchmarks"
              showCreatePlaceholder
            />
            <div className="mt-8">
              <h2 className="mb-4 text-xl font-medium">Benchmark Results</h2>
              {allRunsError ? (
                <Card>
                  <CardContent className="pt-6">
                    <p className="text-destructive text-center">
                      Failed to load benchmark run history.
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <BenchmarkSuiteRunsTable
                  source="benchmark-results"
                  suiteRuns={allSuiteRuns ?? []}
                  showNameColumn
                />
              )}
            </div>
            <div className="h-10" />
          </>
        )}
      </div>
    </div>
  );
};
