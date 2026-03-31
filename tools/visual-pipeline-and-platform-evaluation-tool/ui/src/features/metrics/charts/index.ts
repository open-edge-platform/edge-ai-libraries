/*SPDX-License-Identifier: Apache-2.0*/

export {
  CHART_MAX_DATA_POINTS,
  getRecentYAxisMax,
} from "@/features/metrics/charts/shared";
export type {
  DashboardChartCommonProps,
  DashboardSummarySectionProps,
} from "@/features/metrics/charts/shared";
export { FrameRateChart } from "@/features/metrics/charts/FrameRateChart";
export { MemoryUtilizationChart } from "@/features/metrics/charts/MemoryUtilizationChart";
export { CpuUsageChart } from "@/features/metrics/charts/CpuUsageChart";
export { CpuTemperatureChart } from "@/features/metrics/charts/CpuTemperatureChart";
export { CpuFrequencyChart } from "@/features/metrics/charts/CpuFrequencyChart";
export { GpuUsageChart } from "@/features/metrics/charts/GpuUsageChart";
export { GpuPowerChart } from "@/features/metrics/charts/GpuPowerChart";
export { GpuFrequencyChart } from "@/features/metrics/charts/GpuFrequencyChart";
