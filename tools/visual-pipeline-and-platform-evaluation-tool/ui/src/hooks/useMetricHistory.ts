import { useEffect, useRef, useState } from "react";
import { useMetrics } from "@/features/metrics/useMetrics";

export interface MetricHistoryPoint {
  timestamp: number;
  fps?: number;
  cpu?: number;
  gpu?: number;
  gpu1?: number;
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
        gpu: metrics.gpu,
        gpu1: metrics.gpu1,
      };

      const updated = [...prev, newPoint];

      // Ogranicz do MAX_HISTORY_POINTS najnowszych punktów
      if (updated.length > MAX_HISTORY_POINTS) {
        return updated.slice(updated.length - MAX_HISTORY_POINTS);
      }

      return updated;
    });
  }, [metrics.fps, metrics.cpu, metrics.gpu, metrics.gpu1]);

  return history;
};
