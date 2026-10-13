import type { BenchmarkWorkloadRun, Pipeline } from "@/api/api.generated.ts";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

const CHART_COLORS = [
  "var(--color-green-chart)",
  "var(--color-purple-chart)",
  "var(--color-geode-chart)",
  "var(--color-red-chart)",
  "var(--color-magenta-chart)",
  "var(--color-yellow-chart)",
] as const;

type SummaryMetricKey = "total_fps" | "latency_avg_ms" | "power_usage";

type WorkloadSummaryChartSeries = {
  key: string;
  label: string;
  color: string;
};

type WorkloadSummaryChartDatum = {
  streams: number;
  [seriesKey: string]: number;
};

type WorkloadSummaryChartDefinition = {
  title: string;
  metricKey: SummaryMetricKey;
  formatValue: (value: number) => string;
  allowDecimals?: boolean;
};

type BenchmarkTestCaseRun = BenchmarkWorkloadRun["test_case_runs"][number];

const getMetricValue = (
  testCaseRun: BenchmarkTestCaseRun,
  metricKey: SummaryMetricKey,
) => {
  const metricValue = testCaseRun[metricKey];
  return typeof metricValue === "number" ? metricValue : 0;
};

const buildWorkloadSummaryChart = (
  workloadRun: BenchmarkWorkloadRun,
  pipeline?: Pipeline,
  metricKey: SummaryMetricKey = "total_fps",
): {
  data: WorkloadSummaryChartDatum[];
  series: WorkloadSummaryChartSeries[];
  config: ChartConfig;
} => {
  const seriesByKey = new Map<string, WorkloadSummaryChartSeries>();

  pipeline?.variants.forEach((variant, index) => {
    seriesByKey.set(variant.id, {
      key: variant.id,
      label: variant.name,
      color: CHART_COLORS[index % CHART_COLORS.length],
    });
  });

  workloadRun.test_case_runs.forEach((testCaseRun) => {
    if (!seriesByKey.has(testCaseRun.variant_id)) {
      seriesByKey.set(testCaseRun.variant_id, {
        key: testCaseRun.variant_id,
        label: testCaseRun.variant_id,
        color:
          CHART_COLORS[seriesByKey.size % CHART_COLORS.length] ??
          CHART_COLORS[0],
      });
    }
  });

  const hasNpuSeries = Array.from(seriesByKey.values()).some((variant) =>
    variant.label.toLowerCase().includes("npu"),
  );

  if (!hasNpuSeries) {
    seriesByKey.set("npu-placeholder", {
      key: "npu-placeholder",
      label: "NPU",
      color: "#94a3b8",
    });
  }

  const series = Array.from(seriesByKey.values());

  const config = series.reduce<ChartConfig>((acc, item) => {
    acc[item.key] = {
      label: item.label,
      color: item.color,
    };
    return acc;
  }, {});

  const groupedByStreams = new Map<number, WorkloadSummaryChartDatum>();

  for (const testCaseRun of workloadRun.test_case_runs) {
    if (!groupedByStreams.has(testCaseRun.streams)) {
      const initialValues = Object.fromEntries(
        series.map((item) => [item.key, 0]),
      ) as Record<string, number>;

      groupedByStreams.set(testCaseRun.streams, {
        streams: testCaseRun.streams,
        ...initialValues,
      });
    }

    const row = groupedByStreams.get(testCaseRun.streams);
    if (!row) continue;

    const matchingSeries = seriesByKey.get(testCaseRun.variant_id);
    const seriesKey = matchingSeries?.key ?? testCaseRun.variant_id;
    row[seriesKey] = getMetricValue(testCaseRun, metricKey);
  }

  return {
    data: Array.from(groupedByStreams.values()).sort(
      (left, right) => left.streams - right.streams,
    ),
    series,
    config,
  };
};

type BenchmarkWorkloadSummaryChartProps = {
  workloadRun: BenchmarkWorkloadRun;
  pipeline?: Pipeline;
} & WorkloadSummaryChartDefinition;

export const BenchmarkWorkloadSummaryChart = ({
  workloadRun,
  pipeline,
  title,
  metricKey,
  formatValue,
  allowDecimals = false,
}: BenchmarkWorkloadSummaryChartProps) => {
  const {
    data: chartData,
    series,
    config: chartConfig,
  } = useMemo(
    () => buildWorkloadSummaryChart(workloadRun, pipeline, metricKey),
    [workloadRun, pipeline, metricKey],
  );

  if (chartData.length === 0) {
    return (
      <div className="border bg-background p-4 text-sm text-muted-foreground">
        No summary chart data available.
      </div>
    );
  }

  return (
    <div className="border bg-background p-4">
      <div className="mb-4 flex items-start justify-between gap-3">
        <h3 className="font-medium">{title}</h3>
      </div>
      <ChartContainer config={chartConfig} className="h-[18rem] w-full">
        <BarChart
          data={chartData}
          margin={{ top: 8, right: 8, left: 0, bottom: 8 }}
        >
          <CartesianGrid
            vertical={false}
            strokeDasharray="3 3"
            opacity={0.35}
          />
          <XAxis
            dataKey="streams"
            tickLine={false}
            axisLine={false}
            tickMargin={10}
            interval={0}
            stroke="#737373"
            tickFormatter={(value) => `${value}`}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            allowDecimals={allowDecimals}
            stroke="#737373"
            tickFormatter={(value) => formatValue(Number(value))}
            width={100}
          />
          <ChartTooltip
            content={
              <ChartTooltipContent
                labelFormatter={(value) => `Streams: ${value}`}
                formatter={(value, name) => {
                  const numericValue =
                    typeof value === "number" ? value : Number(value);
                  const label = chartConfig[name as string]?.label || name;
                  return `${label}: ${formatValue(numericValue)}`;
                }}
              />
            }
          />
          {series.map((item) => (
            <Bar
              key={item.key}
              dataKey={item.key}
              fill={`var(--color-${item.key})`}
              stroke={`var(--color-${item.key})`}
              fillOpacity={0.35}
              strokeWidth={1.5}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          ))}
          <ChartLegend content={<ChartLegendContent />} />
        </BarChart>
      </ChartContainer>
    </div>
  );
};
