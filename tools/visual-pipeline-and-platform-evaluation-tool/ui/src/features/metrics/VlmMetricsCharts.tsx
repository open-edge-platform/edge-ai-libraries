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
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 min-w-0">
      <MetricChart
        title="VLM TTFT Over Time"
        data={data}
        dataKeys={["ttft"]}
        colors={["var(--color-orange-chart)"]}
        unit=" ms"
        yAxisDomain={[0, getVlmYAxisMax(data, "ttft")]}
        showLegend={false}
        labels={["TTFT"]}
        maxDataPoints={CHART_MAX_DATA_POINTS}
        isSummary={isSummary}
      />
      <MetricChart
        title="VLM TPOT Over Time"
        data={data}
        dataKeys={["tpot"]}
        colors={["var(--color-green-chart)"]}
        unit=" ms"
        yAxisDomain={[0, getVlmYAxisMax(data, "tpot")]}
        showLegend={false}
        labels={["TPOT"]}
        maxDataPoints={CHART_MAX_DATA_POINTS}
        isSummary={isSummary}
      />
      <MetricChart
        title="VLM Total Latency Over Time"
        data={data}
        dataKeys={["totalLatency"]}
        colors={["var(--color-red-chart)"]}
        unit=" ms"
        yAxisDomain={[0, getVlmYAxisMax(data, "totalLatency")]}
        showLegend={false}
        labels={["Generation"]}
        maxDataPoints={CHART_MAX_DATA_POINTS}
        isSummary={isSummary}
      />
    </div>
  );
};
