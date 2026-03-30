/*SPDX-License-Identifier: Apache-2.0*/

import { MetricChart } from "@/features/metrics/MetricChart";
import {
  CHART_MAX_DATA_POINTS,
  type DashboardChartCommonProps,
} from "@/features/metrics/charts";

interface FrameRateChartProps extends DashboardChartCommonProps {
  data: Array<{ timestamp: number; value: number }>;
  yAxisMax: number;
}

export const FrameRateChart = ({
  data,
  yAxisMax,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
}: FrameRateChartProps) => {
  return (
    <MetricChart
      title="Frame Rate Over Time"
      data={data}
      dataKeys={["value"]}
      colors={["var(--color-magenta-chart)"]}
      unit=" fps"
      yAxisDomain={[0, yAxisMax]}
      showLegend={false}
      labels={["Frame Rate"]}
      maxDataPoints={CHART_MAX_DATA_POINTS}
      isSummary={isSummary}
      forceDark={forceDark}
      useDemoStyles={useDemoStyles}
    />
  );
};
