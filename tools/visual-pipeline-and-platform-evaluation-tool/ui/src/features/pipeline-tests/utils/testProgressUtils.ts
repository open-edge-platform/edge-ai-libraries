/*SPDX-License-Identifier: Apache-2.0*/

export const CHART_MAX_DATA_POINTS = 30;

export const GPU_ENGINE_KEYS = [
  "compute",
  "render",
  "copy",
  "video",
  "videoEnhance",
] as const;

export type GpuEngineKey = (typeof GPU_ENGINE_KEYS)[number];

export const ENGINE_COLORS: Record<GpuEngineKey, string> = {
  compute: "var(--color-yellow-chart)",
  render: "var(--color-orange-chart)",
  copy: "var(--color-purple-chart)",
  video: "var(--color-red-chart)",
  videoEnhance: "var(--color-geode-chart)",
};

export const ENGINE_LABELS: Record<GpuEngineKey, string> = {
  compute: "Compute",
  render: "Render",
  copy: "Copy",
  video: "Video",
  videoEnhance: "Video Enhance",
};

export const getRecentYAxisMax = (
  values: number[],
  maxDataPoints: number,
  minMax: number,
  headroomFactor = 1.15,
): number => {
  const recentValues = values.slice(-maxDataPoints).filter(Number.isFinite);
  if (recentValues.length === 0) return minMax;

  const recentMax = Math.max(...recentValues, 0);
  if (recentMax <= 0) return minMax;

  return Math.max(recentMax * headroomFactor, minMax);
};
