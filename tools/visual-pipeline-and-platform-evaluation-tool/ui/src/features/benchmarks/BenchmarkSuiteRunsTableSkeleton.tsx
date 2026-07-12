import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type BenchmarkSuiteRunsTableSkeletonProps = {
  showNameColumn?: boolean;
};

export const BenchmarkSuiteRunsTableSkeleton = ({
  showNameColumn = false,
}: BenchmarkSuiteRunsTableSkeletonProps) => {
  return (
    <Table className="border rounded-lg">
      <TableHeader className="bg-muted">
        <TableRow>
          <TableHead className="w-max"></TableHead>
          {showNameColumn ? (
            <TableHead className="w-max">Name</TableHead>
          ) : null}
          <TableHead className="w-max">Date</TableHead>
          <TableHead className="w-max">Duration</TableHead>
          <TableHead className="w-max">Overall score</TableHead>
          <TableHead className="w-max">Performance score</TableHead>
          <TableHead className="w-max">Efficiency score</TableHead>
          <TableHead className="w-max">Pass rate</TableHead>
          <TableHead className="w-[3.125rem]">Status</TableHead>
          <TableHead className="w-[3.5rem]"></TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {Array.from({ length: 4 }).map((_, idx) => (
          <TableRow key={`suite-runs-skeleton-${idx}`}>
            <TableCell>
              <Skeleton className="mx-auto h-4 w-10" />
            </TableCell>
            {showNameColumn ? (
              <TableCell>
                <Skeleton className="h-4 w-28" />
              </TableCell>
            ) : null}
            <TableCell>
              <Skeleton className="h-4 w-40" />
            </TableCell>
            <TableCell>
              <Skeleton className="h-4 w-20" />
            </TableCell>
            <TableCell>
              <Skeleton className="h-4 w-16" />
            </TableCell>
            <TableCell>
              <Skeleton className="h-4 w-16" />
            </TableCell>
            <TableCell>
              <Skeleton className="h-4 w-16" />
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
        ))}
      </TableBody>
    </Table>
  );
};
