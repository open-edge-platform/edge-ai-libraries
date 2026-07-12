import { Fragment } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export const BenchmarkSuiteRunDetailsTableSkeleton = () => {
  return (
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
          <Fragment key={`run-details-skeleton-${idx}`}>
            <TableRow>
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
            <TableRow>
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
          </Fragment>
        ))}
      </TableBody>
    </Table>
  );
};
