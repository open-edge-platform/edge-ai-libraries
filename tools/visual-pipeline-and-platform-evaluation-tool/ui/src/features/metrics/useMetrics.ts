import { useRef } from "react";
import { useAppSelector } from "@/store/hooks.ts";
import {
  selectCpuMetric,
  selectCpuMetrics,
  selectFpsMetric,
  selectGpuMetrics,
  selectMemoryMetric,
  selectMetrics,
} from "@/store/reducers/metrics.ts";

export const useMetrics = () => {
  const fps = useAppSelector(selectFpsMetric);
  const cpu = useAppSelector(selectCpuMetric);
  const cpuDetailed = useAppSelector(selectCpuMetrics);
  const memory = useAppSelector(selectMemoryMetric);
  const allMetrics = useAppSelector(selectMetrics);
  const previousAvailableGpuIdsRef = useRef<string[]>([]);
  const previousGpuUsageRef = useRef<Record<string, number>>({});
  const gpuZeroStreakRef = useRef<Record<string, number>>({});

  // dynamically get all available GPU IDs
  const rawAvailableGpuIds = Array.from(
    new Set(
      allMetrics
        .filter((m) => m.name === "gpu_engine_usage" && m.tags?.gpu_id)
        .map((m) => m.tags!.gpu_id!),
    ),
  ).sort();

  if (rawAvailableGpuIds.length > 0) {
    previousAvailableGpuIdsRef.current = rawAvailableGpuIds;
  }

  const availableGpuIds =
    rawAvailableGpuIds.length > 0
      ? rawAvailableGpuIds
      : previousAvailableGpuIdsRef.current;

  // get detailed metrics for all GPUs
  const gpuDetailedMetrics = useAppSelector((state) => {
    const gpus: Record<string, ReturnType<typeof selectGpuMetrics>> = {};
    availableGpuIds.forEach((gpuId) => {
      gpus[gpuId] = selectGpuMetrics(state, gpuId);
    });
    return gpus;
  });

  // transform GPU metrics to array format for components
  const gpus = availableGpuIds.map((gpuId) => {
    const metrics = gpuDetailedMetrics[gpuId];
    // calculate overall usage from engine usages
    const engineUsages = [
      metrics?.compute ?? 0,
      metrics?.render ?? 0,
      metrics?.copy ?? 0,
      metrics?.video ?? 0,
      metrics?.videoEnhance ?? 0,
    ];
    const rawUsage =
      engineUsages.length > 0
        ? Math.max(...engineUsages) // use max engine usage as overall GPU usage
        : 0;

    const previousUsage = previousGpuUsageRef.current[gpuId] ?? 0;
    const currentZeroStreak = gpuZeroStreakRef.current[gpuId] ?? 0;

    let usage = rawUsage;
    if (rawUsage === 0 && previousUsage > 0) {
      const nextZeroStreak = currentZeroStreak + 1;
      gpuZeroStreakRef.current[gpuId] = nextZeroStreak;
      if (nextZeroStreak === 1) {
        usage = previousUsage;
      }
    } else {
      gpuZeroStreakRef.current[gpuId] = 0;
    }

    if (rawUsage > 0) {
      previousGpuUsageRef.current[gpuId] = rawUsage;
    }

    return {
      id: gpuId,
      usage,
      ...metrics,
    };
  });

  // get primary GPU usage (first available GPU or 0)
  const gpu = gpus.length > 0 ? gpus[0].usage : 0;

  return {
    fps: fps ?? 0,
    cpu: cpu ?? 0,
    gpu,
    cpuDetailed,
    memory: memory ?? 0,
    availableGpuIds,
    gpuDetailedMetrics,
    gpus,
    npu: 0,
  };
};
