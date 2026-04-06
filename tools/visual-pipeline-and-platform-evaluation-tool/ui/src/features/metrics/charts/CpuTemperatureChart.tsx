/*SPDX-License-Identifier: Apache-2.0*/

import { MetricChart } from "@/features/metrics/MetricChart";
import {
  CHART_MAX_DATA_POINTS,
  type DashboardChartCommonProps,
} from "@/features/metrics/charts";

interface CpuTemperatureChartProps extends DashboardChartCommonProps {
  data: Array<{ timestamp: number; temp: number }>;
  yAxisMax: number;
}

export const CpuTemperatureChart = ({
  data,
  yAxisMax,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
}: CpuTemperatureChartProps) => {
  return (
    <MetricChart
      title="CPU Temperature Over Time"
      data={data}
      dataKeys={["temp"]}
      colors={["var(--color-green-chart)"]}
      unit="°C"
      yAxisDomain={[0, yAxisMax]}
      showLegend={false}
      labels={["Temperature"]}
      maxDataPoints={CHART_MAX_DATA_POINTS}
      isSummary={isSummary}
      forceDark={forceDark}
      useDemoStyles={useDemoStyles}
    />
  );
};
