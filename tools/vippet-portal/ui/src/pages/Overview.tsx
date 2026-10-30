import { Link } from "react-router";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ScoreRadarCharts } from "@/features/overview/ScoreRadarCharts";
import { useGetInstancesQuery } from "@/api/portalApi";
import {
  CARDS_GRID_CLASS,
  CONTENT_CONTAINER_CLASS,
  cpuGeneration,
  formatDeviceName,
} from "@/lib/utils";
import { ChartNoAxesCombined, Cpu, Server, Zap } from "lucide-react";

const PLATFORM_ROWS = [
  { key: "cpu", label: "CPU", icon: Cpu },
  { key: "gpu", label: "GPU", icon: Zap },
  { key: "npu", label: "NPU", icon: Server },
] as const;

export const Overview = () => {
  const { data: instances, isLoading } = useGetInstancesQuery(undefined, {
    pollingInterval: 30_000,
  });

  return (
    <div className={CONTENT_CONTAINER_CLASS}>
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Testbed overview</h1>
          <p className="text-muted-foreground">
            Aggregated results from every registered ViPPET instance.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link to="/instances">Manage instances</Link>
        </Button>
      </div>

      {isLoading ? (
        <div className={CARDS_GRID_CLASS}>
          {[0, 1].map(index => (
            <Skeleton key={index} className="h-56 w-full" />
          ))}
        </div>
      ) : (instances?.length ?? 0) === 0 ? (
        <Card>
          <CardContent className="pt-6 text-center text-muted-foreground">
            No instances registered yet.{" "}
            <Link to="/instances" className="underline underline-offset-2">
              Add the first machine
            </Link>
            .
          </CardContent>
        </Card>
      ) : (
        <div className={CARDS_GRID_CLASS}>
          {instances?.map(instance => {
            return (
              <Card key={instance.id}>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between gap-2">
                    <span className="truncate">{instance.name}</span>
                    {instance.reachable ? (
                      <Badge variant="success">online</Badge>
                    ) : (
                      <Badge variant="destructive">offline</Badge>
                    )}
                  </CardTitle>
                  <CardDescription className="space-y-0.5">
                    <span className="block font-medium text-foreground">
                      {cpuGeneration(instance.cpu) || "Platform unknown"}
                    </span>
                    <span className="block truncate">
                      <a
                        href={instance.url}
                        target="_blank"
                        rel="noreferrer"
                        className="underline underline-offset-2"
                      >
                        {instance.url}
                      </a>
                      {instance.version ? ` · ${instance.version}` : ""}
                    </span>
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="space-y-1 text-sm">
                    {PLATFORM_ROWS.map(({ key, label, icon: Icon }) => (
                      <div key={key} className="flex items-center gap-2">
                        <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                        <span className="w-8 text-muted-foreground">
                          {label}
                        </span>
                        <span className="truncate">
                          {formatDeviceName(instance[key]) || "–"}
                        </span>
                      </div>
                    ))}
                  </div>

                  <div className="grid grid-cols-3 gap-2 border-t pt-3 text-center text-sm">
                    <div>
                      <p className="text-xs text-muted-foreground">
                        Benchmarks
                      </p>
                      <p className="font-semibold">
                        {instance.benchmark_run_count}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">
                        Perf tests
                      </p>
                      <p className="font-semibold">
                        {instance.performance_job_count}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Density</p>
                      <p className="font-semibold">
                        {instance.density_job_count}
                      </p>
                    </div>
                  </div>

                  {instance.error ? (
                    <p className="border-t pt-3 text-xs text-destructive">
                      {instance.error}
                    </p>
                  ) : null}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <div className="mt-10">
        <h2 className="text-xl font-semibold">Benchmark scores by suite</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Most recent completed run per suite and machine. Federal &amp;
          Aerospace, Health &amp; Science and Education are placeholder data —
          no machine publishes those suites yet.
        </p>
        <ScoreRadarCharts />
      </div>

      <div className="mt-8 flex gap-3">
        <Button asChild>
          <Link to="/benchmarks">
            <ChartNoAxesCombined className="h-4 w-4" />
            Compare benchmark runs
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link to="/tests/performance">Compare performance tests</Link>
        </Button>
        <Button asChild variant="outline">
          <Link to="/tests/density">Compare density tests</Link>
        </Button>
      </div>
      <div className="h-10" />
    </div>
  );
};
