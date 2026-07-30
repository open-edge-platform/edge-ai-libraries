import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { BackButton } from "@/components/shared/BackButton";
import { BenchmarkSuiteRunDetailsTableSkeleton } from "@/features/benchmarks/BenchmarkSuiteRunDetailsTableSkeleton.tsx";

type BenchmarkSuiteResultDetailsSkeletonProps = {
  backLinkTo: string;
};

export const BenchmarkSuiteRunDetailsSkeleton = ({
  backLinkTo,
}: BenchmarkSuiteResultDetailsSkeletonProps) => (
  <div className="container pl-16 mx-auto py-10">
    <div className="mb-6">
      <div className="flex items-center gap-4 mb-2">
        <BackButton to={backLinkTo} />
        <Skeleton className="h-9 w-80" />
      </div>
      <div className="ml-14">
        <div className="text-muted-foreground inline-flex items-center gap-2">
          <span>Status:</span>
          <Badge variant="outline">
            <Skeleton className="h-3 w-8" />
          </Badge>
        </div>
      </div>
    </div>

    <div className="mt-6 mb-4 flex items-center gap-2">
      <h1 className="font-medium text-xl">Workloads</h1>
    </div>
    <BenchmarkSuiteRunDetailsTableSkeleton />
  </div>
);
