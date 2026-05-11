import { useEffect, useRef, useState } from "react";
import { useMetrics } from "@/features/metrics/useMetrics";
import { useAppSelector } from "@/store/hooks.ts";
import { selectIsConnected } from "@/store/reducers/metrics.ts";

export interface GpuMetrics {
  compute?: number;
  render?: number;
  copy?: number;
  video?: number;
  videoEnhance?: number;
  frequency?: number;
  gpuPower?: number;
  pkgPower?: number;
}

export interface MetricHistoryPoint {
  timestamp: number;
  fps?: number;
  cpu?: number;
  cpuUser?: number;
  cpuSystem?: number;
  cpuIdle?: number;
  cpuAvgFrequency?: number;
  cpuTemp?: number;
  memory?: number;
  gpus: Record<string, GpuMetrics>;
}

const MAX_HISTORY_POINTS = 60;

export const useMetricHistory = () => {
  const metrics = useMetrics();
  const isConnected = useAppSelector(selectIsConnected);
  const [history, setHistory] = useState<MetricHistoryPoint[]>([]);
  const lastUpdateRef = useRef<number>(0);

  useEffect(() => {
    if (!isConnected) {
      return;
    }

    const now = Date.now();

    if (now - lastUpdateRef.current < 1000) {
      return;
    }

    lastUpdateRef.current = now;

    setHistory((prev) => {
      const gpus: Record<string, GpuMetrics> = {};
      metrics.availableGpuIds.forEach((gpuId) => {
        const gpuMetric = metrics.gpuDetailedMetrics[gpuId];
        gpus[gpuId] = {
          compute: gpuMetric?.compute,
          render: gpuMetric?.render,
          copy: gpuMetric?.copy,
          video: gpuMetric?.video,
          videoEnhance: gpuMetric?.videoEnhance,
          frequency: gpuMetric?.frequency,
          gpuPower: gpuMetric?.gpuPower,
          pkgPower: gpuMetric?.pkgPower,
        };
      });

      const newPoint: MetricHistoryPoint = {
        timestamp: now,
        fps: metrics.fps,
        cpu: metrics.cpu,
        cpuUser: metrics.cpuDetailed.user,
        cpuIdle: metrics.cpuDetailed.idle,
        cpuAvgFrequency: metrics.cpuDetailed.avgFrequency,
        cpuTemp: metrics.cpuDetailed.temp,
        memory: metrics.memory,
        gpus,
      };

      const updated = [...prev, newPoint];

      if (updated.length > MAX_HISTORY_POINTS) {
        return updated.slice(updated.length - MAX_HISTORY_POINTS);
      }

      return updated;
    });
  }, [
    isConnected,
    metrics.fps,
    metrics.cpu,
    metrics.cpuDetailed.user,
    metrics.cpuDetailed.idle,
    metrics.cpuDetailed.avgFrequency,
    metrics.cpuDetailed.temp,
    metrics.memory,
    metrics.availableGpuIds,
    metrics.gpuDetailedMetrics,
  ]);

  return history;
};
