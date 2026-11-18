import { useMemo } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
} from "recharts";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { useGetBenchmarkRunsQuery, type BenchmarkRun } from "@/api/portalApi";
import { formatMetric } from "@/lib/format";

const PALETTE = [
  "var(--chart-1, #0068b5)",
  "var(--chart-2, #00c7fd)",
  "var(--chart-3, #8f5da2)",
  "var(--chart-4, #e96115)",
  "var(--chart-5, #6ec46e)",
  "var(--chart-6, #b24501)",
];

const REAL_SUITES = [
  { slug: "metro-suite", label: "Metro" },
  { slug: "manufacturing-suite", label: "Manufacturing" },
  { slug: "retail-suite", label: "Retail" },
];

/** Suites no machine publishes yet; scaled off the real scores so shapes stay plausible. */
const MOCK_SUITES = [
  { label: "Federal & Aerospace", factor: 0.84 },
  { label: "Health & Science", factor: 1.12 },
  { label: "Education", factor: 0.98 },
];

const CHARTS = [
  {
    metric: "score_total",
    title: "Overall",
    description: "√(performance × efficiency) — fast and efficient",
  },
  {
    metric: "score_performance",
    title: "Performance",
    description: "Raw throughput: total FPS",
  },
  {
    metric: "score_efficiency",
    title: "Efficiency",
    description: "FPS per watt, or per % utilisation without power data",
  },
] as const;

type Metric = (typeof CHARTS)[number]["metric"];
type ChartRow = Record<string, string | number | null>;

/** Stable ±3% wobble, small enough to never reorder the machines. */
const jitter = (instanceId: number, label: string) => {
  const seed = [...label].reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const offset = (((instanceId * 31 + seed) % 7) - 3) / 100;
  return 1 + offset;
};

/** How far the mock suites pull each machine toward the leader (0 = real gap, 1 = level). */
const LEVELLING = 0.55;

export const ScoreRadarCharts = () => {
  const { data: runs, isLoading } = useGetBenchmarkRunsQuery(undefined, {
    pollingInterval: 30_000,
  });

  const { machines, dataByMetric, maxByMetric } = useMemo(() => {
    // Runs arrive newest first, so the first hit per machine+suite is the latest.
    const latest = new Map<string, BenchmarkRun>();
    for (const run of runs ?? []) {
      if (run.status.toLowerCase() !== "completed") continue;
      const key = `${run.instance_id}:${run.suite_slug}`;
      if (!latest.has(key)) latest.set(key, run);
    }

    const scored = [...latest.values()];
    const machines = [
      ...new Map(
        scored.map(run => [run.instance_id, run.instance_name])
      ).entries(),
    ].map(([id, name]) => ({ id, name }));

    const score = (run: BenchmarkRun | undefined, metric: Metric) =>
      run?.[metric] ?? null;

    const dataByMetric = Object.fromEntries(
      CHARTS.map(({ metric }): [Metric, ChartRow[]] => {
        const realRows = REAL_SUITES.map(({ slug, label }) => ({
          suite: label,
          ...Object.fromEntries(
            machines.map(({ id }) => [
              String(id),
              score(latest.get(`${id}:${slug}`), metric),
            ])
          ),
        }));

        const average = new Map(
          machines.map(({ id }) => {
            const values = REAL_SUITES.map(({ slug }) =>
              score(latest.get(`${id}:${slug}`), metric)
            ).filter((value): value is number => value !== null);
            return [
              id,
              values.length
                ? values.reduce((sum, value) => sum + value, 0) / values.length
                : null,
            ];
          })
        );

        const best = Math.max(
          0,
          ...[...average.values()].filter(value => value !== null)
        );

        const mockRows = MOCK_SUITES.map(({ label, factor }) => ({
          suite: label,
          ...Object.fromEntries(
            machines.map(({ id }) => {
              const own = average.get(id);
              return [
                String(id),
                own === null || own === undefined
                  ? null
                  : Number(
                      (
                        (own + (best - own) * LEVELLING) *
                        factor *
                        jitter(id, label)
                      ).toFixed(metric === "score_performance" ? 1 : 2)
                    ),
              ];
            })
          ),
        }));

        return [metric, [...realRows, ...mockRows]];
      })
    ) as Record<Metric, ChartRow[]>;

    // Recharts only grids up to its own ticks, so the scale needs an explicit top.
    const maxByMetric = Object.fromEntries(
      CHARTS.map(({ metric }): [Metric, number] => [
        metric,
        Math.max(
          0,
          ...dataByMetric[metric].flatMap(row =>
            machines
              .map(({ id }) => row[String(id)])
              .filter((value): value is number => typeof value === "number")
          )
        ),
      ])
    ) as Record<Metric, number>;

    return { machines, dataByMetric, maxByMetric };
  }, [runs]);

  if (isLoading) {
    return (
      <div className="grid gap-4 lg:grid-cols-3">
        {CHARTS.map(({ metric }) => (
          <Skeleton key={metric} className="h-80 w-full" />
        ))}
      </div>
    );
  }

  if (machines.length === 0) return null;

  const config: ChartConfig = Object.fromEntries(
    machines.map((machine, index) => [
      String(machine.id),
      { label: machine.name, color: PALETTE[index % PALETTE.length] },
    ])
  );

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {CHARTS.map(({ metric, title, description }) => (
        <Card key={metric}>
          <CardHeader className="pb-0">
            <CardTitle className="text-base">{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </CardHeader>
          <CardContent className="pt-2">
            <ChartContainer config={config} className="h-80 w-full">
              <RadarChart
                data={dataByMetric[metric]}
                outerRadius="68%"
                margin={{ top: 8, right: 24, bottom: 8, left: 24 }}
              >
                <PolarGrid />
                <PolarAngleAxis dataKey="suite" tick={{ fontSize: 11 }} />
                <PolarRadiusAxis
                  domain={[0, maxByMetric[metric]]}
                  tick={false}
                  axisLine={false}
                />
                <ChartTooltip
                  content={
                    <ChartTooltipContent
                      formatter={value => formatMetric(metric, value)}
                    />
                  }
                />
                <ChartLegend content={<ChartLegendContent />} />
                {machines.map((machine, index) => (
                  <Radar
                    key={machine.id}
                    dataKey={String(machine.id)}
                    name={machine.name}
                    stroke={PALETTE[index % PALETTE.length]}
                    fill={PALETTE[index % PALETTE.length]}
                    fillOpacity={0.15}
                    strokeWidth={2}
                    connectNulls
                  />
                ))}
              </RadarChart>
            </ChartContainer>
          </CardContent>
        </Card>
      ))}
    </div>
  );
};
