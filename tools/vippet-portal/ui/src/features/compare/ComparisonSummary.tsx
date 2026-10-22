import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/utils";
import { formatDeviceName } from "@/lib/utils";
import { formatTimestamp } from "@/lib/timeUtils";
import {
  computeDelta,
  formatDelta,
  formatMetric,
  metricLabel,
} from "@/lib/format";
import type { Comparison } from "@/api/portalApi";

/** One card per compared result, with deltas measured against the first card. */
export const ComparisonSummary = ({
  comparison,
  metrics,
}: {
  comparison: Comparison;
  metrics: string[];
}) => {
  const baseline = comparison.columns[0];

  return (
    <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(18.75rem,1fr))]">
      {comparison.columns.map((column, index) => (
        <Card key={column.ref}>
          <CardHeader>
            <CardTitle className="flex items-center justify-between gap-2">
              <span className="truncate">{column.instance_name}</span>
              <StatusBadge status={column.status} />
            </CardTitle>
            <p className="truncate text-xs text-muted-foreground">
              {formatDeviceName(column.cpu)}
            </p>
            <p className="text-xs text-muted-foreground">
              {column.label}
              {column.start_time
                ? ` · ${formatTimestamp(column.start_time)}`
                : ""}
              {index === 0 ? " · baseline" : ""}
            </p>
          </CardHeader>
          <CardContent className="space-y-1">
            {metrics.map((metric) => {
              const delta =
                index === 0
                  ? null
                  : computeDelta(
                      metric,
                      column.summary[metric],
                      baseline?.summary[metric],
                    );
              return (
                <div
                  key={metric}
                  className="flex items-baseline justify-between gap-2 text-sm"
                >
                  <span className="text-muted-foreground">
                    {metricLabel(metric)}
                  </span>
                  <span className="flex items-baseline gap-2 tabular-nums">
                    <span className="font-medium">
                      {formatMetric(metric, column.summary[metric])}
                    </span>
                    {delta && delta.percent !== 0 ? (
                      <span
                        className={cn(
                          "text-xs",
                          delta.better ? "text-success" : "text-destructive",
                        )}
                      >
                        {formatDelta(delta)}
                      </span>
                    ) : null}
                  </span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      ))}
    </div>
  );
};
