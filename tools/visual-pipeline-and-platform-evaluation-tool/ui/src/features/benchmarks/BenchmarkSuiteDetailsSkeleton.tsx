import { Link } from "react-router";
import { ArrowLeft } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

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
          <Link
            to={source === "dashboard" ? "/" : "/benchmarks"}
            className="size-8 flex items-center justify-center hover:bg-accent dark:hover:bg-accent/50 transition-colors"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
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

      <Table className="border rounded-lg">
        <TableHeader className="bg-muted">
          <TableRow>
            <TableHead className="w-32"></TableHead>
            <TableHead className="w-max">Pipeline Name</TableHead>
            <TableHead>Description</TableHead>
            <TableHead className="w-max">Variants</TableHead>
            <TableHead className="w-max">Details</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: 3 }).map((_, idx) => (
            <TableRow key={`workload-skeleton-${idx}`}>
              <TableCell>
                <Skeleton className="h-16 w-32" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-36" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-full max-w-[60%]" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-28" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-16" />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <div className="mt-6 mb-4 flex items-center gap-2">
        <h1 className="font-medium text-xl">Benchmark Results</h1>
      </div>

      <Table className="border rounded-lg">
        <TableHeader className="bg-muted">
          <TableRow>
            <TableHead className="w-max"></TableHead>
            <TableHead className="w-max">Date</TableHead>
            <TableHead className="w-max">Duration</TableHead>
            <TableHead className="w-max">Overall score</TableHead>
            <TableHead className="w-max">Performance score</TableHead>
            <TableHead className="w-max">Efficiency score</TableHead>
            <TableHead className="w-max">Pass rate</TableHead>
            <TableHead className="w-max">Status</TableHead>
            <TableHead className="w-max"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: 3 }).map((_, idx) => (
            <TableRow key={`previous-runs-skeleton-${idx}`}>
              <TableCell>
                <Skeleton className="h-4 w-12" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-28" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-20" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-24" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-28" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-24" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-20" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-16" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-8" />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
};
