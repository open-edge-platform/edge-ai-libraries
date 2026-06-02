import { MetricChart } from "@/features/metrics/MetricChart";
import {
  CHART_MAX_DATA_POINTS,
  type DashboardChartCommonProps,
} from "@/features/metrics/charts";

interface NpuFrequencyChartProps extends DashboardChartCommonProps {
  data: Array<{ timestamp: number; frequency: number }>;
  yAxisMax: number;
}

export const NpuFrequencyChart = ({
  data,
  yAxisMax,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
}: NpuFrequencyChartProps) => {
  return (
    <MetricChart
      title="NPU Frequency Over Time"
      data={data}
      dataKeys={["frequency"]}
      colors={["var(--color-purple-chart)"]}
      unit="MHz"
      yAxisDomain={[0, yAxisMax]}
      showLegend={false}
      labels={["Frequency"]}
      maxDataPoints={CHART_MAX_DATA_POINTS}
      isSummary={isSummary}
      forceDark={forceDark}
      useDemoStyles={useDemoStyles}
    />
  );
};
