import { Fragment } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import {
  computeDelta,
  formatDelta,
  formatMetric,
  metricDirection,
  toNumber,
} from "@/lib/format";
import type { Comparison } from "@/api/portalApi";

type ComparisonMatrixProps = {
  comparison: Comparison;
  metric: string;
  showDelta: boolean;
};

const bestRefForRow = (
  row: Comparison["rows"][number],
  refs: string[],
  metric: string
): string | null => {
  const candidates = refs
    .map(ref => ({ ref, value: toNumber(row.cells[ref]?.[metric]) }))
    .filter(
      (entry): entry is { ref: string; value: number } => entry.value !== null
    );
  if (candidates.length < 2) return null;

  const preferHigher = metricDirection(metric) === "higher-is-better";
  return candidates.reduce((best, entry) =>
    preferHigher
      ? entry.value > best.value
        ? entry
        : best
      : entry.value < best.value
        ? entry
        : best
  ).ref;
};

/**
 * Aligned matrix of workloads (rows) against compared results (columns).
 * The first column is the baseline that deltas are measured from.
 */
export const ComparisonMatrix = ({
  comparison,
  metric,
  showDelta,
}: ComparisonMatrixProps) => {
  const refs = comparison.columns.map(column => column.ref);
  const baselineRef = refs[0];
  let lastGroup: string | null = null;

  return (
    <Table className="border rounded-lg">
      <TableHeader className="bg-muted">
        <TableRow>
          <TableHead className="min-w-[16rem]">Workload</TableHead>
          {comparison.columns.map(column => (
            <TableHead key={column.ref} className="text-right">
              <div className="font-medium">{column.instance_name}</div>
              <div className="text-xs font-normal text-muted-foreground">
                {column.label}
              </div>
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {comparison.rows.map(row => {
          const groupHeader =
            row.group && row.group !== lastGroup ? row.group : null;
          lastGroup = row.group ?? lastGroup;
          const bestRef = bestRefForRow(row, refs, metric);
          const isSuiteRow = row.key.endsWith("::_suite_");

          return (
            <Fragment key={row.key}>
              {groupHeader ? (
                <TableRow className="bg-muted/40">
                  <TableCell
                    colSpan={refs.length + 1}
                    className="font-semibold text-sm"
                  >
                    {groupHeader}
                  </TableCell>
                </TableRow>
              ) : null}
              <TableRow>
                <TableCell
                  className={cn("pl-6", isSuiteRow && "font-medium italic")}
                >
                  {isSuiteRow ? "Workload total" : row.label}
                </TableCell>
                {refs.map(ref => {
                  const cell = row.cells[ref];
                  const value = cell?.[metric];
                  const delta =
                    showDelta && ref !== baselineRef
                      ? computeDelta(
                          metric,
                          value,
                          row.cells[baselineRef]?.[metric]
                        )
                      : null;

                  return (
                    <TableCell key={ref} className="text-right tabular-nums">
                      {cell ? (
                        <div className="flex items-baseline justify-end gap-2">
                          <span
                            className={cn(
                              bestRef === ref && "font-semibold text-success"
                            )}
                          >
                            {formatMetric(metric, value)}
                          </span>
                          {delta && delta.percent !== 0 ? (
                            <span
                              className={cn(
                                "text-xs",
                                delta.better
                                  ? "text-success"
                                  : "text-destructive"
                              )}
                            >
                              {formatDelta(delta)}
                            </span>
                          ) : null}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">not run</span>
                      )}
                    </TableCell>
                  );
                })}
              </TableRow>
            </Fragment>
          );
        })}
        {comparison.rows.length === 0 ? (
          <TableRow>
            <TableCell
              colSpan={refs.length + 1}
              className="text-center text-muted-foreground"
            >
              No comparable results.
            </TableCell>
          </TableRow>
        ) : null}
      </TableBody>
    </Table>
  );
};
