/*SPDX-License-Identifier: Apache-2.0*/

import { MetricChart } from "@/features/metrics/MetricChart";
import {
  CHART_MAX_DATA_POINTS,
  type DashboardChartCommonProps,
} from "@/features/metrics/charts";

interface CpuUsageChartProps extends DashboardChartCommonProps {
  data: Array<{ timestamp: number; user: number }>;
}

export const CpuUsageChart = ({
  data,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
}: CpuUsageChartProps) => {
  return (
    <MetricChart
      title="CPU Usage Over Time"
      data={data}
      dataKeys={["user"]}
      colors={["var(--color-green-chart)"]}
      unit="%"
      yAxisDomain={[0, 100]}
      showLegend={false}
      labels={["CPU Usage"]}
      maxDataPoints={CHART_MAX_DATA_POINTS}
      isSummary={isSummary}
      forceDark={forceDark}
      useDemoStyles={useDemoStyles}
    />
  );
};
