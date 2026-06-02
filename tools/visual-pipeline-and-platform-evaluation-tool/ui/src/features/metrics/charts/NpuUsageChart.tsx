import { MetricChart } from "@/features/metrics/MetricChart";
import {
  CHART_MAX_DATA_POINTS,
  type DashboardChartCommonProps,
} from "@/features/metrics/charts";

interface NpuUsageChartProps extends DashboardChartCommonProps {
  data: Array<{ timestamp: number; usage: number }>;
}

export const NpuUsageChart = ({
  data,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
}: NpuUsageChartProps) => {
  return (
    <MetricChart
      title="NPU Usage Over Time"
      data={data}
      dataKeys={["usage"]}
      colors={["var(--color-geode-chart)"]}
      unit="%"
      yAxisDomain={[0, 100]}
      showLegend={false}
      labels={["NPU Usage"]}
      maxDataPoints={CHART_MAX_DATA_POINTS}
      isSummary={isSummary}
      forceDark={forceDark}
      useDemoStyles={useDemoStyles}
    />
  );
};
