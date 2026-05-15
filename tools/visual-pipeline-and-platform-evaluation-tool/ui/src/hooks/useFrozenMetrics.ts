import { useCallback, useMemo, useRef, useState } from "react";
import {
  useMetricHistory,
  type GpuMetrics,
  type MetricHistoryPoint,
} from "@/hooks/useMetricHistory";

export interface FrozenMetricsSummary {
  fps: number;
  cpu: number;
  memory: number;
  availableGpuIds: string[];
  gpuDetailedMetrics: Record<string, GpuMetrics>;
  latencyAvg?: number;
  latencyMin?: number;
  latencyMax?: number;
}

export interface FrozenSnapshotOverrides {
  fps?: number | null;
  latencyAvg?: number;
  latencyMin?: number;
  latencyMax?: number;
}

/**
 * Aggregate per-stream latency_tracer_metrics from job status
 * into a single avg/min/max suitable for FrozenSnapshotOverrides.
 */
export function aggregateLatencyTracerMetrics(
  metrics: Record<string, { avg_ms: number; min_ms: number; max_ms: number }> | null | undefined,
): Pick<FrozenSnapshotOverrides, "latencyAvg" | "latencyMin" | "latencyMax"> | undefined {
  if (!metrics) return undefined;
  const entries = Object.values(metrics);
  if (entries.length === 0) return undefined;
  return {
    latencyAvg: entries.reduce((s, e) => s + e.avg_ms, 0) / entries.length,
    latencyMin: Math.min(...entries.map((e) => e.min_ms)),
    latencyMax: Math.max(...entries.map((e) => e.max_ms)),
  };
}

export function useFrozenMetrics() {
  const history = useMetricHistory();
  const [snapshot, setSnapshot] = useState<MetricHistoryPoint[]>([]);
  const [resultFps, setResultFps] = useState<number | null>(null);
  const [resultLatency, setResultLatency] = useState<{
    avg?: number;
    min?: number;
    max?: number;
  } | null>(null);
  const testStartTimestampRef = useRef<number | null>(null);
  const historyRef = useRef<MetricHistoryPoint[]>(history);

  historyRef.current = history;

  const ensureChartRenderable = useCallback(
    (points: MetricHistoryPoint[]): MetricHistoryPoint[] => {
      if (points.length >= 2) {
        return points;
      }

      if (points.length === 1) {
        const singlePoint = points[0];
        return [
          { ...singlePoint, timestamp: singlePoint.timestamp - 1000 },
          singlePoint,
        ];
      }

      return [];
    },
    [],
  );

  /** Call immediately before triggering a test run. */
  const startRecording = useCallback(() => {
    testStartTimestampRef.current = Date.now();
    setSnapshot([]);
    setResultFps(null);
    setResultLatency(null);
  }, []);

  /**
   * Call once the test job has finished (COMPLETED or FAILED).
   * Pass overrides from the job result to replace SSE-computed averages.
   */
  const freezeSnapshot = useCallback(
    (overrides?: FrozenSnapshotOverrides | null) => {
      const currentHistory = historyRef.current;
      const ts = testStartTimestampRef.current;
      if (ts != null) {
        const filteredSnapshot = currentHistory.filter(
          (p) => p.timestamp >= ts,
        );

        if (filteredSnapshot.length > 0) {
          setSnapshot(ensureChartRenderable(filteredSnapshot));
        } else if (currentHistory.length > 0) {
          const latestPoint = currentHistory.at(-1);
          setSnapshot(latestPoint ? ensureChartRenderable([latestPoint]) : []);
        } else {
          setSnapshot([]);
        }
      }
      setResultFps(overrides?.fps ?? null);
      setResultLatency(
        overrides?.latencyAvg !== undefined
          ? {
              avg: overrides.latencyAvg,
              min: overrides.latencyMin,
              max: overrides.latencyMax,
            }
          : null,
      );
    },
    [ensureChartRenderable],
  );

  /** Reset all frozen state (e.g. when starting a new pipeline/test). */
  const clear = useCallback(() => {
    testStartTimestampRef.current = null;
    setSnapshot([]);
    setResultFps(null);
    setResultLatency(null);
  }, []);

  const frozenSummary = useMemo<FrozenMetricsSummary | null>(() => {
    if (snapshot.length === 0) return null;

    const avg = (values: number[]) =>
      values.length > 0 ? values.reduce((s, v) => s + v, 0) / values.length : 0;

    const fpsSeries = snapshot.map((p) => p.fps ?? 0);
    const firstPos = fpsSeries.findIndex((v) => v > 0);
    const fpsSlice = firstPos >= 0 ? fpsSeries.slice(firstPos) : fpsSeries;
    const lastFps = fpsSlice.at(-1) ?? 0;

    const gpuIds = Array.from(
      new Set(snapshot.flatMap((p) => Object.keys(p.gpus ?? {}))),
    ).sort();

    const gpuDetailedMetrics = gpuIds.reduce<Record<string, GpuMetrics>>(
      (acc, gpuId) => {
        const pts = snapshot.map((p) => p.gpus[gpuId]);
        const m = (key: keyof GpuMetrics) =>
          avg(
            pts
              .map((p) => p?.[key])
              .filter((v): v is number => v !== undefined),
          );
        acc[gpuId] = {
          compute: m("compute"),
          render: m("render"),
          copy: m("copy"),
          video: m("video"),
          videoEnhance: m("videoEnhance"),
          frequency: m("frequency"),
          gpuPower: m("gpuPower"),
          pkgPower: m("pkgPower"),
        };
        return acc;
      },
      {},
    );

    const lastPoint = snapshot.at(-1);

    return {
      fps: resultFps ?? lastFps,
      cpu: avg(snapshot.map((p) => p.cpu ?? 0)),
      memory: avg(snapshot.map((p) => p.memory ?? 0)),
      availableGpuIds: gpuIds,
      gpuDetailedMetrics,
      latencyAvg: resultLatency?.avg ?? lastPoint?.latencyAvg,
      latencyMin: resultLatency?.min ?? lastPoint?.latencyMin,
      latencyMax: resultLatency?.max ?? lastPoint?.latencyMax,
    };
  }, [snapshot, resultFps, resultLatency]);

  return {
    frozenHistory: snapshot,
    frozenSummary,
    startRecording,
    freezeSnapshot,
    clear,
  };
}
