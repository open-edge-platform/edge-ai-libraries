import { useGetBenchmarksQuery } from "@/api/api.generated";
import { Card, CardContent } from "@/components/ui/card";
import { BenchmarkCards } from "@/features/benchmarks/BenchmarkCards";
import { PipelineCardsLoader } from "@/features/pipelines/PipelineCardsLoader";

export const Benchmarks = () => {
  const { data: benchmarks, isLoading, error } = useGetBenchmarksQuery();

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-4">
        {isLoading ? (
          <PipelineCardsLoader count={10} />
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
          <BenchmarkCards
            benchmarks={benchmarks}
            source="benchmarks"
            showCreatePlaceholder
          />
        )}
      </div>
    </div>
  );
};
