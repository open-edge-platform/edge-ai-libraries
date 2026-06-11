import { MetricChart } from "@/features/metrics/MetricChart";
import {
  CHART_MAX_DATA_POINTS,
  type DashboardChartCommonProps,
} from "@/features/metrics/charts";

interface LatencyChartProps extends DashboardChartCommonProps {
  data: Array<{
    timestamp: number;
    avg: number;
    min: number;
    max: number;
  }>;
  yAxisMax: number;
}

export const LatencyChart = ({
  data,
  yAxisMax,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
}: LatencyChartProps) => {
  return (
    <MetricChart
      title="Latency Over Time"
      data={data}
      dataKeys={["avg", "min", "max"]}
      colors={[
        "var(--color-orange-chart)",
        "var(--color-green-chart)",
        "var(--color-red-chart)",
      ]}
      unit=" ms"
      yAxisDomain={[0, yAxisMax]}
      showLegend={true}
      labels={["Avg", "Min", "Max"]}
      maxDataPoints={CHART_MAX_DATA_POINTS}
      isSummary={isSummary}
      forceDark={forceDark}
      useDemoStyles={useDemoStyles}
    />
  );
};
