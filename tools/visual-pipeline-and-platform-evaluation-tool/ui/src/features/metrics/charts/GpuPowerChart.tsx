/*SPDX-License-Identifier: Apache-2.0*/

import { GpuChartSection } from "@/features/metrics/charts/GpuChartSection";
import {
  type DashboardChartCommonProps,
  type DashboardSummarySectionProps,
} from "@/features/metrics/charts";

interface GpuPowerChartProps
  extends DashboardChartCommonProps,
    DashboardSummarySectionProps {
  data: Array<{ timestamp: number; gpuPower: number; pkgPower: number }>;
  yAxisMax: number;
  selectedGpu: number;
  availableGpus: number[];
  onGpuChange: (gpu: number) => void;
}

export const GpuPowerChart = ({
  data,
  yAxisMax,
  selectedGpu,
  availableGpus,
  onGpuChange,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
  summarySectionClassName,
  summaryTitleClassName,
}: GpuPowerChartProps) => {
  return (
    <GpuChartSection
      title="Power Usage Over Time"
      chartData={data}
      chartDataKeys={["gpuPower", "pkgPower"]}
      chartColors={["var(--color-red-chart)", "var(--color-yellow-chart)"]}
      chartUnit=" W"
      chartYAxisDomain={[0, yAxisMax]}
      chartLabels={["GPU Power", "Package Power"]}
      selectedGpu={selectedGpu}
      availableGpus={availableGpus}
      onGpuChange={onGpuChange}
      isSummary={isSummary}
      forceDark={forceDark}
      useDemoStyles={useDemoStyles}
      summarySectionClassName={summarySectionClassName}
      summaryTitleClassName={summaryTitleClassName}
    />
  );
};
