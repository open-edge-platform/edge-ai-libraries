import { type BenchmarkSuite } from "@/api/api.generated";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import thumbnailPlaceholder from "@/assets/thumbnail_placeholder.png";
import { Link } from "react-router";
import { CARDS_GRID_CLASS, cn } from "@/lib/utils";
import { Plus } from "lucide-react";

const getBenchmarkTestCount = (benchmark: BenchmarkSuite): number => {
  return benchmark.workloads.reduce(
    (total, workload) => total + workload.test_cases.length,
    0,
  );
};

type BenchmarkCardsProps = {
  benchmarks: BenchmarkSuite[];
  maxCards?: number;
  showCreatePlaceholder?: boolean;
  source: "dashboard" | "benchmarks";
};

export const BenchmarkCards = ({
  benchmarks,
  maxCards,
  showCreatePlaceholder = false,
  source,
}: BenchmarkCardsProps) => {
  const displayedBenchmarks =
    maxCards !== undefined ? benchmarks.slice(0, maxCards) : benchmarks;

  return (
    <div className={CARDS_GRID_CLASS}>
      {showCreatePlaceholder && (
        <button
          type="button"
          disabled
          className="w-full h-full min-h-[12.5rem] border-2 border-dashed border-border transition-all flex flex-col items-center justify-center gap-3 text-muted-foreground/70 cursor-not-allowed"
        >
          <Plus className="w-12 h-12" />
          <span className="text-lg font-medium">Create Benchmark</span>
          <span className="text-sm">Coming soon</span>
        </button>
      )}
      {displayedBenchmarks.map((benchmark) => (
        <Card
          key={benchmark.id}
          className={cn(
            "flex flex-col pt-0 transition-all duration-200 overflow-hidden",
            "hover:-translate-y-1 hover:shadow-md",
          )}
        >
          <Link to={`/benchmarks/${benchmark.slug}?source=${source}`}>
            <img
              src={thumbnailPlaceholder}
              alt={benchmark.name}
              className="w-full object-cover"
            />
          </Link>
          <CardHeader className="space-y-2">
            <CardTitle
              className="flex items-center justify-between gap-2 truncate min-w-0 overflow-hidden"
              title={benchmark.name}
            >
              <Link
                to={`/benchmarks/${benchmark.slug}?source=${source}`}
                className="hover:underline block truncate"
              >
                {benchmark.name}
              </Link>
              <Badge variant="outline" className="shrink-0">
                {getBenchmarkTestCount(benchmark)} tests
              </Badge>
            </CardTitle>
            <CardDescription className="line-clamp-6 break-words text-justify">
              {benchmark.description}
            </CardDescription>
          </CardHeader>
        </Card>
      ))}
    </div>
  );
};
