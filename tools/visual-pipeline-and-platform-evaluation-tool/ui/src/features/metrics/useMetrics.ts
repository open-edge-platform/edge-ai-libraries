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

  // dynamically get all available GPU IDs
  const availableGpuIds = Array.from(
    new Set(
      allMetrics
        .filter((m) => m.name === "gpu_engine_usage" && m.tags?.gpu_id)
        .map((m) => m.tags!.gpu_id!),
    ),
  ).sort();

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
    const usage =
      engineUsages.length > 0
        ? Math.max(...engineUsages) // use max engine usage as overall GPU usage
        : 0;

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
