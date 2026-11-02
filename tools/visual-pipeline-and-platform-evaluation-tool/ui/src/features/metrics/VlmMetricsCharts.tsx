import {
  MetricChart,
  type MetricDataPoint,
} from "@/features/metrics/MetricChart.tsx";
import {
  CHART_MAX_DATA_POINTS,
  getRecentYAxisMax,
} from "@/features/metrics/charts";

export interface VlmMetricsPoint extends MetricDataPoint {
  ttft: number;
  tpot: number;
  totalLatency: number;
}

const getVlmYAxisMax = (
  data: VlmMetricsPoint[],
  key: keyof Pick<VlmMetricsPoint, "ttft" | "tpot" | "totalLatency">,
) =>
  Math.ceil(
    getRecentYAxisMax(
      data.map((point) => point[key]),
      CHART_MAX_DATA_POINTS,
      100,
    ) * 1.15,
  );

export const VlmMetricsCharts = ({
  data,
  isSummary = false,
}: {
  data: VlmMetricsPoint[];
  isSummary?: boolean;
}) => {
  if (data.length === 0) {
    return (
      <div className="min-h-[100px] flex items-center justify-center border bg-muted/20 p-3">
        <p className="text-sm text-muted-foreground">
          Waiting for VLM metrics...
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 min-w-0">
      <MetricChart
        title="VLM Total Latency Over Time"
        data={data}
        dataKeys={["totalLatency"]}
        colors={["var(--color-red-chart)"]}
        unit=" ms"
        yAxisDomain={[0, getVlmYAxisMax(data, "totalLatency")]}
        showLegend={false}
        labels={["VLM Total Latency"]}
        titleTooltip={[
          {
            label: "VLM Total Latency",
            description:
              "Total time from the start of generation until the response is complete.",
          },
          {
            label: "TTFT",
            description:
              "Time from the request starting until the first token is generated; indicates initial response latency.",
          },
          {
            label: "TPOT",
            description:
              "Average time between generated tokens; indicates streaming generation speed.",
          },
        ]}
        additionalTooltipMetrics={[
          {
            dataKey: "ttft",
            label: "VLM TTFT",
          },
          {
            dataKey: "tpot",
            label: "VLM TPOT",
          },
        ]}
        maxDataPoints={CHART_MAX_DATA_POINTS}
        isSummary={isSummary}
      />
    </div>
  );
};
