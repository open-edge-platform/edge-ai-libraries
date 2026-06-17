import { MetricChart } from "@/features/metrics/MetricChart";
import {
  CHART_MAX_DATA_POINTS,
  type DashboardChartCommonProps,
} from "@/features/metrics/charts";

interface NpuPowerChartProps extends DashboardChartCommonProps {
  data: Array<{ timestamp: number; power: number }>;
  yAxisMax: number;
}

export const NpuPowerChart = ({
  data,
  yAxisMax,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
}: NpuPowerChartProps) => {
  return (
    <MetricChart
      title="NPU Power Over Time"
      data={data}
      dataKeys={["power"]}
      colors={["var(--color-orange-chart)"]}
      unit="W"
      yAxisDomain={[0, yAxisMax]}
      showLegend={false}
      labels={["Power"]}
      maxDataPoints={CHART_MAX_DATA_POINTS}
      isSummary={isSummary}
      forceDark={forceDark}
      useDemoStyles={useDemoStyles}
    />
  );
};
