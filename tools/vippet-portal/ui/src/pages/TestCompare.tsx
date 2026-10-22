import { useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { ArrowLeft } from "lucide-react";
import { useCompareTestJobsQuery, type TestKind } from "@/api/portalApi";
import { ComparisonSummary } from "@/features/compare/ComparisonSummary";
import { ComparisonMatrix } from "@/features/compare/ComparisonMatrix";
import { ComparisonChart } from "@/features/compare/ComparisonChart";
import { MetricSelect } from "@/features/compare/MetricSelect";
import { CONTENT_CONTAINER_CLASS } from "@/lib/utils";
import { chartMetricTitle } from "@/lib/format";

const SUMMARY_METRICS = [
  "total_fps",
  "per_stream_fps",
  "total_streams",
  "elapsed_time",
];

export const TestCompare = () => {
  const { pathname } = useLocation();
  const kind: TestKind = pathname.includes("/density")
    ? "density"
    : "performance";
  const [searchParams] = useSearchParams();
  const refs = searchParams.getAll("refs");
  const [metric, setMetric] = useState(
    kind === "density" ? "total_streams" : "total_fps",
  );
  const [showDelta, setShowDelta] = useState(true);

  const { data, isLoading, error } = useCompareTestJobsQuery(
    { kind, refs },
    { skip: refs.length === 0 },
  );

  const listPath = `/tests/${kind}`;

  return (
    <div className={CONTENT_CONTAINER_CLASS}>
      <div className="mb-6 flex items-center gap-4">
        <Button asChild variant="outline" size="icon" aria-label="Back">
          <Link to={listPath}>
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <h1 className="text-3xl font-bold capitalize">{kind} comparison</h1>
      </div>

      {refs.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center text-muted-foreground">
            Select {kind} tests on the{" "}
            <Link to={listPath} className="underline underline-offset-2">
              {kind}
            </Link>{" "}
            page first.
          </CardContent>
        </Card>
      ) : isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : error || !data ? (
        <Card>
          <CardContent className="pt-6 text-center text-destructive">
            Failed to build the comparison.
          </CardContent>
        </Card>
      ) : (
        <>
          {Object.keys(data.errors).length > 0 ? (
            <Card className="mb-6 border-destructive">
              <CardContent className="pt-6 text-sm text-destructive">
                {Object.entries(data.errors).map(([ref, message]) => (
                  <p key={ref}>
                    {ref}: {message}
                  </p>
                ))}
              </CardContent>
            </Card>
          ) : null}

          <ComparisonSummary comparison={data} metrics={SUMMARY_METRICS} />

          <div className="mt-8 mb-4 flex flex-wrap items-center justify-between gap-4">
            <h2 className="text-xl font-medium">{chartMetricTitle(metric)}</h2>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Switch
                  id="show-delta"
                  checked={showDelta}
                  onCheckedChange={setShowDelta}
                />
                <Label htmlFor="show-delta">Show delta vs baseline</Label>
              </div>
              <MetricSelect
                metrics={data.metrics}
                value={metric}
                onChange={setMetric}
              />
            </div>
          </div>

          <ComparisonChart comparison={data} metric={metric} />

          <h2 className="mt-8 mb-4 text-xl font-medium">
            Per-workload results
          </h2>
          <ComparisonMatrix
            comparison={data}
            metric={metric}
            showDelta={showDelta}
          />
        </>
      )}
      <div className="h-10" />
    </div>
  );
};
