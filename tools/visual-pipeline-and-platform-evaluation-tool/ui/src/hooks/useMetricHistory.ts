import { useEffect, useRef, useState } from "react";
import { useMetrics } from "@/features/metrics/useMetrics";

export interface MetricHistoryPoint {
  timestamp: number;
  fps?: number;
  cpu?: number;
  cpuUser?: number;
  cpuSystem?: number;
  cpuIdle?: number;
  gpu?: number;
  gpu1?: number;
  gpu0Compute?: number;
  gpu0Render?: number;
  gpu0Video?: number;
  gpu0VideoEnhance?: number;
  gpu1Compute?: number;
  gpu1Render?: number;
  gpu1Video?: number;
  gpu1VideoEnhance?: number;
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
      const newPoint: MetricHistoryPoint = {
        timestamp: now,
        fps: metrics.fps,
        cpu: metrics.cpu,
        cpuUser: metrics.cpuDetailed.user,
        cpuSystem: metrics.cpuDetailed.system,
        cpuIdle: metrics.cpuDetailed.idle,
        gpu: metrics.gpu,
        gpu1: metrics.gpu1,
        gpu0Compute: metrics.gpu0Detailed.compute,
        gpu0Render: metrics.gpu0Detailed.render,
        gpu0Video: metrics.gpu0Detailed.video,
        gpu0VideoEnhance: metrics.gpu0Detailed.videoEnhance,
        gpu1Compute: metrics.gpu1Detailed.compute,
        gpu1Render: metrics.gpu1Detailed.render,
        gpu1Video: metrics.gpu1Detailed.video,
        gpu1VideoEnhance: metrics.gpu1Detailed.videoEnhance,
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
    metrics.gpu,
    metrics.gpu1,
    metrics.gpu0Detailed.compute,
    metrics.gpu0Detailed.render,
    metrics.gpu0Detailed.video,
    metrics.gpu0Detailed.videoEnhance,
    metrics.gpu1Detailed.compute,
    metrics.gpu1Detailed.render,
    metrics.gpu1Detailed.video,
    metrics.gpu1Detailed.videoEnhance,
  ]);

  return history;
};
