// SPDX-License-Identifier: Apache-2.0
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
}

/**
 * Encapsulates the "freeze metrics on test completion" pattern.
 *
 * Usage:
 *   const { frozenHistory, frozenSummary, startRecording, freezeSnapshot, clear } = useFrozenMetrics();
 *
 *   // Before starting a test:
 *   startRecording();
 *
 *   // After test completes (pass the result FPS from the job if available):
 *   freezeSnapshot(status.total_fps ?? status.per_stream_fps);
 *   // or for density tests:
 *   freezeSnapshot(status.per_stream_fps);
 *
 *   // To reset (e.g. when navigating away):
 *   clear();
 *
 *   // Pass to MetricsDashboard when test is finished:
 *   <MetricsDashboard
 *     historyOverride={frozenHistory.length > 0 ? frozenHistory : undefined}
 *     metricsOverride={frozenSummary ?? undefined}
 *   />
 */
export function useFrozenMetrics() {
  const history = useMetricHistory();
  const [snapshot, setSnapshot] = useState<MetricHistoryPoint[]>([]);
  const [resultFps, setResultFps] = useState<number | null>(null);
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
  }, []);

  /**
   * Call once the test job has finished (COMPLETED or FAILED).
   * Pass the FPS from the job result to override the WS-computed average.
   */
  const freezeSnapshot = useCallback(
    (fps?: number | null) => {
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
      setResultFps(fps ?? null);
    },
    [ensureChartRenderable],
  );

  /** Reset all frozen state (e.g. when starting a new pipeline/test). */
  const clear = useCallback(() => {
    testStartTimestampRef.current = null;
    setSnapshot([]);
    setResultFps(null);
  }, []);

  const frozenSummary = useMemo<FrozenMetricsSummary | null>(() => {
    if (snapshot.length === 0) return null;

    const avg = (values: number[]) =>
      values.length > 0 ? values.reduce((s, v) => s + v, 0) / values.length : 0;

    const fpsSeries = snapshot.map((p) => p.fps ?? 0);
    const firstPos = fpsSeries.findIndex((v) => v > 0);
    const fpsSlice = firstPos >= 0 ? fpsSeries.slice(firstPos) : fpsSeries;
    const fpsAvg = avg(fpsSlice);

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

    return {
      fps: resultFps ?? fpsAvg,
      cpu: avg(snapshot.map((p) => p.cpu ?? 0)),
      memory: avg(snapshot.map((p) => p.memory ?? 0)),
      availableGpuIds: gpuIds,
      gpuDetailedMetrics,
    };
  }, [snapshot, resultFps]);

  return {
    frozenHistory: snapshot,
    frozenSummary,
    startRecording,
    freezeSnapshot,
    clear,
  };
}
