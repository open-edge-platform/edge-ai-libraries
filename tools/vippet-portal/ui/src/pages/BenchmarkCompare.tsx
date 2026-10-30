import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowLeft } from "lucide-react";
import { useCompareBenchmarkRunsQuery } from "@/api/portalApi";
import { ComparisonSummary } from "@/features/compare/ComparisonSummary";
import { ComparisonMatrix } from "@/features/compare/ComparisonMatrix";
import { ComparisonChart } from "@/features/compare/ComparisonChart";
import { MetricSelect } from "@/features/compare/MetricSelect";
import { CONTENT_CONTAINER_CLASS } from "@/lib/utils";
import { chartMetricTitle } from "@/lib/format";

const SUMMARY_METRICS = [
  "score_total",
  "score_performance",
  "score_efficiency",
  "pass_rate",
  "execution_time",
];

export const BenchmarkCompare = () => {
  const [searchParams] = useSearchParams();
  const refs = searchParams.getAll("refs");
  const [metric, setMetric] = useState("total_fps");
  const [showDelta, setShowDelta] = useState(true);
  const [workload, setWorkload] = useState<string | null>(null);

  const { data, isLoading, error } = useCompareBenchmarkRunsQuery(refs, {
    skip: refs.length === 0,
  });

  const workloads = useMemo(
    () => [
      ...new Set(
        (data?.rows ?? [])
          .map(row => row.group)
          .filter((group): group is string => Boolean(group))
      ),
    ],
    [data]
  );

  // Falls back to the first workload until one is picked, and after the
  // selection stops existing because a different set of runs was compared.
  const activeWorkload =
    workload && workloads.includes(workload) ? workload : (workloads[0] ?? "");

  const visible = useMemo(() => {
    if (!data) return data;
    return {
      ...data,
      rows: data.rows.filter(row => row.group === activeWorkload),
    };
  }, [data, activeWorkload]);

  return (
    <div className={CONTENT_CONTAINER_CLASS}>
      <div className="mb-6 flex items-center gap-4">
        <Button asChild variant="outline" size="icon" aria-label="Back">
          <Link to="/benchmarks">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <h1 className="text-3xl font-bold">Benchmark comparison</h1>
      </div>

      {refs.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center text-muted-foreground">
            Select runs on the{" "}
            <Link to="/benchmarks" className="underline underline-offset-2">
              Benchmarks
            </Link>{" "}
            page first.
          </CardContent>
        </Card>
      ) : isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : error || !data || !visible ? (
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
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-2">
                <Switch
                  id="show-delta"
                  checked={showDelta}
                  onCheckedChange={setShowDelta}
                />
                <Label htmlFor="show-delta">Show delta vs baseline</Label>
              </div>
              <Select value={activeWorkload} onValueChange={setWorkload}>
                <SelectTrigger className="w-[16rem]">
                  <SelectValue placeholder="Workload" />
                </SelectTrigger>
                <SelectContent>
                  {workloads.map(name => (
                    <SelectItem key={name} value={name}>
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <MetricSelect
                metrics={data.metrics}
                value={metric}
                onChange={setMetric}
              />
            </div>
          </div>

          <ComparisonChart comparison={visible} metric={metric} />

          <h2 className="mt-8 mb-4 text-xl font-medium">Per-test results</h2>
          <ComparisonMatrix
            comparison={visible}
            metric={metric}
            showDelta={showDelta}
          />
        </>
      )}
      <div className="h-10" />
    </div>
  );
};
