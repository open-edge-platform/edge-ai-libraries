/*SPDX-License-Identifier: Apache-2.0*/

import { useMemo } from "react";
import type { GpuMetrics, MetricHistoryPoint } from "@/hooks/useMetricHistory.ts";
import {
  CHART_MAX_DATA_POINTS,
  ENGINE_COLORS,
  ENGINE_LABELS,
  GPU_ENGINE_KEYS,
  type GpuEngineKey,
  getRecentYAxisMax,
  stabilizeSingleZeroDropOptionalSeries,
  stabilizeSingleZeroDropSeries,
} from "@/features/pipeline-tests/utils/testProgressUtils";

export interface TestProgressMetricsSnapshot {
  fps: number;
  cpu: number;
  memory: number;
  availableGpuIds: string[];
  gpuDetailedMetrics: Record<string, GpuMetrics>;
}

interface UseTestProgressDataParams {
  history: MetricHistoryPoint[];
  metrics: TestProgressMetricsSnapshot;
  selectedGpu: number;
}

interface OptionalGpuUsagePoint {
  timestamp: number;
  compute?: number;
  render?: number;
  copy?: number;
  video?: number;
  videoEnhance?: number;
}

export const useTestProgressData = ({
  history,
  metrics,
  selectedGpu,
}: UseTestProgressDataParams) => {
  const availableGpus = useMemo(
    () => metrics.availableGpuIds.map((id) => Number.parseInt(id, 10)),
    [metrics.availableGpuIds],
  );

  const fpsData = useMemo(
    () =>
      history.map((point) => ({
        timestamp: point.timestamp,
        value: point.fps ?? 0,
      })),
    [history],
  );

  const cpuData = useMemo(
    () =>
      history.map((point) => ({
        timestamp: point.timestamp,
        user: point.cpuUser ?? 0,
      })),
    [history],
  );

  const gpuData = useMemo(() => {
    const gpuId = selectedGpu.toString();
    const rawGpuData: OptionalGpuUsagePoint[] = history.map((point) => {
      const gpu = point.gpus[gpuId];
      return {
        timestamp: point.timestamp,
        compute: gpu?.compute,
        render: gpu?.render,
        copy: gpu?.copy,
        video: gpu?.video,
        videoEnhance: gpu?.videoEnhance,
      };
    });

    return stabilizeSingleZeroDropOptionalSeries(rawGpuData, [
      "compute",
      "render",
      "copy",
      "video",
      "videoEnhance",
    ]);
  }, [history, selectedGpu]);

  const availableEngines = useMemo(() => {
    const engines: GpuEngineKey[] = [];

    GPU_ENGINE_KEYS.forEach((key) => {
      if (gpuData.some((point) => point[key] !== undefined)) {
        engines.push(key);
      }
    });

    return engines;
  }, [gpuData]);

  const gpuChartData = useMemo(() => {
    const normalizedGpuChartData: Array<{ timestamp: number } & Record<string, number>> =
      gpuData.map((point) => {
        const chartPoint: { timestamp: number } & Record<string, number> = {
          timestamp: point.timestamp,
        };

        availableEngines.forEach((engine) => {
          chartPoint[engine] = point[engine] ?? 0;
        });

        return chartPoint;
      });

    return stabilizeSingleZeroDropSeries(normalizedGpuChartData, availableEngines);
  }, [gpuData, availableEngines]);

  const gpuFrequencyData = useMemo(() => {
    const gpuId = selectedGpu.toString();
    const rawGpuFrequencyData = history.map((point) => ({
      timestamp: point.timestamp,
      frequency: point.gpus[gpuId]?.frequency ?? 0,
    }));

    return stabilizeSingleZeroDropSeries(rawGpuFrequencyData, ["frequency"]);
  }, [history, selectedGpu]);

  const gpuPowerData = useMemo(() => {
    const gpuId = selectedGpu.toString();
    const rawGpuPowerData = history.map((point) => ({
      timestamp: point.timestamp,
      gpuPower: point.gpus[gpuId]?.gpuPower ?? 0,
      pkgPower: point.gpus[gpuId]?.pkgPower ?? 0,
    }));

    return stabilizeSingleZeroDropSeries(rawGpuPowerData, ["gpuPower", "pkgPower"]);
  }, [history, selectedGpu]);

  const displayedGpuUsage = useMemo(() => {
    const latestGpuPoint = gpuData.at(-1);
    if (!latestGpuPoint) {
      const gpuMetrics = metrics.gpuDetailedMetrics[selectedGpu.toString()];
      if (!gpuMetrics) return 0;
      return Math.max(
        gpuMetrics.compute ?? 0,
        gpuMetrics.render ?? 0,
        gpuMetrics.copy ?? 0,
        gpuMetrics.video ?? 0,
        gpuMetrics.videoEnhance ?? 0,
      );
    }

    return Math.max(
      latestGpuPoint.compute ?? 0,
      latestGpuPoint.render ?? 0,
      latestGpuPoint.copy ?? 0,
      latestGpuPoint.video ?? 0,
      latestGpuPoint.videoEnhance ?? 0,
    );
  }, [gpuData, metrics.gpuDetailedMetrics, selectedGpu]);

  const cpuTempData = useMemo(
    () =>
      history.map((point) => ({
        timestamp: point.timestamp,
        temp: point.cpuTemp ?? 0,
      })),
    [history],
  );

  const cpuFrequencyData = useMemo(
    () =>
      history.map((point) => ({
        timestamp: point.timestamp,
        frequency: point.cpuAvgFrequency ?? 0,
      })),
    [history],
  );

  const memoryData = useMemo(
    () =>
      history.map((point) => ({
        timestamp: point.timestamp,
        memory: point.memory ?? 0,
      })),
    [history],
  );

  const fpsYAxisMax = useMemo(
    () =>
      getRecentYAxisMax(
        fpsData.map((point) => point.value),
        CHART_MAX_DATA_POINTS,
        1,
      ),
    [fpsData],
  );

  const cpuTempYAxisMax = useMemo(
    () =>
      getRecentYAxisMax(
        cpuTempData.map((point) => point.temp),
        CHART_MAX_DATA_POINTS,
        1,
      ),
    [cpuTempData],
  );

  const cpuFrequencyYAxisMax = useMemo(
    () =>
      getRecentYAxisMax(
        cpuFrequencyData.map((point) => point.frequency),
        CHART_MAX_DATA_POINTS,
        0.1,
      ),
    [cpuFrequencyData],
  );

  const gpuPowerYAxisMax = useMemo(
    () =>
      getRecentYAxisMax(
        gpuPowerData.map((point) => Math.max(point.gpuPower, point.pkgPower)),
        CHART_MAX_DATA_POINTS,
        1,
      ),
    [gpuPowerData],
  );

  const gpuFrequencyYAxisMax = useMemo(
    () =>
      getRecentYAxisMax(
        gpuFrequencyData.map((point) => point.frequency),
        CHART_MAX_DATA_POINTS,
        0.1,
      ),
    [gpuFrequencyData],
  );

  return {
    availableGpus,
    fpsData,
    cpuData,
    gpuChartData,
    gpuFrequencyData,
    gpuPowerData,
    displayedGpuUsage,
    cpuTempData,
    cpuFrequencyData,
    memoryData,
    fpsYAxisMax,
    cpuTempYAxisMax,
    cpuFrequencyYAxisMax,
    gpuPowerYAxisMax,
    gpuFrequencyYAxisMax,
    availableEngines,
    engineColors: ENGINE_COLORS,
    engineLabels: ENGINE_LABELS,
  };
};
