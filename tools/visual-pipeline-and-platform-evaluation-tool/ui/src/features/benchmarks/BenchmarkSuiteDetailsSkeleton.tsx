import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { BackButton } from "@/components/shared/BackButton";
import { BenchmarkSuiteRunsTableSkeleton } from "@/features/benchmarks/BenchmarkSuiteRunsTableSkeleton.tsx";
import { BenchmarkSuiteWorkloadsTableSkeleton } from "@/features/benchmarks/BenchmarkSuiteWorkloadsTableSkeleton";

type BenchmarkSuiteDetailsSkeletonProps = {
  source: string | null;
};

export const BenchmarkSuiteDetailsSkeleton = ({
  source,
}: BenchmarkSuiteDetailsSkeletonProps) => {
  return (
    <div className="container pl-16 mx-auto py-10">
      <div className="mb-6">
        <div className="flex items-center gap-4 mb-2">
          <BackButton to={source === "dashboard" ? "/" : "/benchmarks"} />
          <Skeleton className="h-9 w-80" />
        </div>
        <div className="ml-14">
          <Skeleton className="h-4 w-[60%]" />
        </div>
      </div>

      <div className="mb-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <h1 className="font-medium text-xl">Workloads</h1>
          <Badge variant="outline">...</Badge>
        </div>
        <Skeleton className="h-9 w-36" />
      </div>

      <BenchmarkSuiteWorkloadsTableSkeleton />

      <div className="mt-6 mb-4 flex items-center gap-2">
        <h1 className="font-medium text-xl">Benchmark Results</h1>
      </div>
      <BenchmarkSuiteRunsTableSkeleton />
    </div>
  );
};
