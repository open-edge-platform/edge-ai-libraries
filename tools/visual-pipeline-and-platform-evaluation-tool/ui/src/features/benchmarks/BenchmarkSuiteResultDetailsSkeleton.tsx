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

type BenchmarkSuiteResultDetailsSkeletonProps = {
  suiteSlug: string;
  backHref: string;
};

export const BenchmarkSuiteResultDetailsSkeleton = ({
  suiteSlug,
  backHref,
}: BenchmarkSuiteResultDetailsSkeletonProps) => {
  return (
    <div className="container pl-16 mx-auto py-10">
      <div className="mb-6">
        <div className="flex items-center gap-4 mb-2">
          <Link
            to={`/benchmarks/${suiteSlug}${backHref}`}
            className="size-8 flex items-center justify-center hover:bg-accent dark:hover:bg-accent/50 transition-colors"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <Skeleton className="h-9 w-80" />
        </div>
        <div className="ml-14">
          <p className="text-muted-foreground inline-flex items-center gap-2">
            <span>Status:</span>
            <Badge variant="outline">
              <Skeleton className="h-3 w-8" />
            </Badge>
          </p>
        </div>
      </div>

      <div className="mt-6 mb-4 flex items-center gap-2">
        <h1 className="font-medium text-xl">Workloads</h1>
      </div>

      <Table className="border rounded-lg">
        <TableHeader className="bg-muted">
          <TableRow>
            <TableHead className="w-10"></TableHead>
            <TableHead className="w-32"></TableHead>
            <TableHead className="w-max">Pipeline Name</TableHead>
            <TableHead className="w-max">Overall score</TableHead>
            <TableHead className="w-max">Performance score</TableHead>
            <TableHead className="w-max">Efficiency score</TableHead>
            <TableHead className="w-max">Duration</TableHead>
            <TableHead className="w-max">Pass rate</TableHead>
            <TableHead className="w-[3.125rem]">Status</TableHead>
            <TableHead className="w-[3.5rem]"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: 2 }).map((_, idx) => (
            <>
              <TableRow key={`run-details-parent-skeleton-${idx}`}>
                <TableCell>
                  <Skeleton className="h-7 w-7" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-16 w-32" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-4 w-36" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-4 w-20" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-4 w-20" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-4 w-24" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-4 w-20" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-4 w-20" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-4 w-16" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-7 w-7" />
                </TableCell>
              </TableRow>
              <TableRow key={`run-details-expanded-skeleton-${idx}`}>
                <TableCell colSpan={10} className="bg-muted/25 px-12">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Variant</TableHead>
                        <TableHead>Streams</TableHead>
                        <TableHead>Duration</TableHead>
                        <TableHead>Total FPS</TableHead>
                        <TableHead>Per-stream FPS</TableHead>
                        <TableHead>CPU</TableHead>
                        <TableHead>GPU</TableHead>
                        <TableHead>NPU</TableHead>
                        <TableHead>Media</TableHead>
                        <TableHead>Memory</TableHead>
                        <TableHead>Power</TableHead>
                        <TableHead className="w-[3.125rem]">Status</TableHead>
                        <TableHead className="w-[1.25rem]"></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {Array.from({ length: 2 }).map((__, nestedIdx) => (
                        <TableRow
                          key={`run-details-testcase-skeleton-${idx}-${nestedIdx}`}
                        >
                          <TableCell>
                            <Skeleton className="h-4 w-28" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="h-4 w-10" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="h-4 w-16" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="h-4 w-14" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="h-4 w-14" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="h-4 w-12" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="h-4 w-12" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="h-4 w-10" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="h-4 w-10" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="h-4 w-14" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="h-4 w-12" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="h-4 w-14" />
                          </TableCell>
                          <TableCell>
                            <Skeleton className="h-7 w-7" />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableCell>
              </TableRow>
            </>
          ))}
        </TableBody>
      </Table>
    </div>
  );
};
