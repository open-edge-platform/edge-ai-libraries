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

export const stabilizeSingleZeroDropSeries = <
  T extends object,
  K extends keyof T,
>(
  data: T[],
  keys: K[],
): T[] => {
  const previousByKey: Partial<Record<K, number>> = {};
  const zeroStreakByKey: Partial<Record<K, number>> = {};

  return data.map((point) => {
    const stabilizedPoint = { ...point };

    keys.forEach((key) => {
      const value = point[key] as number;
      const previousValue = previousByKey[key] ?? 0;
      const currentZeroStreak = zeroStreakByKey[key] ?? 0;

      if (value === 0 && previousValue > 0) {
        const nextZeroStreak = currentZeroStreak + 1;
        zeroStreakByKey[key] = nextZeroStreak;
        if (nextZeroStreak === 1) {
          stabilizedPoint[key] = previousValue as T[K];
          return;
        }
      } else {
        zeroStreakByKey[key] = 0;
      }

      if (value > 0) {
        previousByKey[key] = value;
      }
    });

    return stabilizedPoint;
  });
};

export const stabilizeSingleZeroDropOptionalSeries = <
  T extends object,
  K extends keyof T,
>(
  data: T[],
  keys: K[],
): T[] => {
  const previousByKey: Partial<Record<K, number>> = {};
  const zeroStreakByKey: Partial<Record<K, number>> = {};

  return data.map((point) => {
    const stabilizedPoint = { ...point };

    keys.forEach((key) => {
      const value = point[key] as number | undefined;
      if (value === undefined) return;

      const previousValue = previousByKey[key] ?? 0;
      const currentZeroStreak = zeroStreakByKey[key] ?? 0;

      if (value === 0 && previousValue > 0) {
        const nextZeroStreak = currentZeroStreak + 1;
        zeroStreakByKey[key] = nextZeroStreak;
        if (nextZeroStreak === 1) {
          stabilizedPoint[key] = previousValue as T[K];
          return;
        }
      } else {
        zeroStreakByKey[key] = 0;
      }

      if (value > 0) {
        previousByKey[key] = value;
      }
    });

    return stabilizedPoint;
  });
};
