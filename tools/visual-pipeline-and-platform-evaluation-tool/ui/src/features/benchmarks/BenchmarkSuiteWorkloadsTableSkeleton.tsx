import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export const BenchmarkSuiteWorkloadsTableSkeleton = () => {
  return (
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
  );
};
