import { useEffect, useRef, useState } from "react";
import { useMetrics } from "@/features/metrics/useMetrics";

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

const MAX_HISTORY_POINTS = 60; // Przechowuj ostatnie 60 punktów (np. 1 minuta przy 1 pomiar/s)

export const useMetricHistory = () => {
  const metrics = useMetrics();
  const [history, setHistory] = useState<MetricHistoryPoint[]>([]);
  const lastUpdateRef = useRef<number>(0);

  useEffect(() => {
    const now = Date.now();

    // Aktualizuj tylko co sekundę, aby nie przeciążać wykresu
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
        cpuSystem: metrics.cpuDetailed.system,
        cpuIdle: metrics.cpuDetailed.idle,
        cpuAvgFrequency: metrics.cpuDetailed.avgFrequency,
        cpuTemp: metrics.cpuDetailed.temp,
        memory: metrics.memory,
        gpus,
      };

      const updated = [...prev, newPoint];

      // Ogranicz do MAX_HISTORY_POINTS najnowszych punktów
      if (updated.length > MAX_HISTORY_POINTS) {
        return updated.slice(updated.length - MAX_HISTORY_POINTS);
      }

      return updated;
    });
  }, [
    metrics.fps,
    metrics.cpu,
    metrics.cpuDetailed.user,
    metrics.cpuDetailed.system,
    metrics.cpuDetailed.idle,
    metrics.cpuDetailed.avgFrequency,
    metrics.cpuDetailed.temp,
    metrics.memory,
    metrics.availableGpuIds,
    metrics.gpuDetailedMetrics,
  ]);

  return history;
};
