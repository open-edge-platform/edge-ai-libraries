/*SPDX-License-Identifier: Apache-2.0*/

import { MetricChart } from "@/features/metrics/MetricChart";
import {
  CHART_MAX_DATA_POINTS,
  type DashboardChartCommonProps,
} from "@/features/metrics/charts";

interface MemoryUtilizationChartProps extends DashboardChartCommonProps {
  data: Array<{ timestamp: number; memory: number }>;
}

export const MemoryUtilizationChart = ({
  data,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
}: MemoryUtilizationChartProps) => {
  return (
    <MetricChart
      title="Memory Utilization Over Time"
      data={data}
      dataKeys={["memory"]}
      colors={["var(--color-magenta-chart)"]}
      unit="%"
      yAxisDomain={[0, 100]}
      showLegend={false}
      labels={["Memory"]}
      maxDataPoints={CHART_MAX_DATA_POINTS}
      isSummary={isSummary}
      forceDark={forceDark}
      useDemoStyles={useDemoStyles}
    />
  );
};
