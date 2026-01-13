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

  // Dynamically get all available GPU IDs
  let availableGpuIds = Array.from(
    new Set(
      allMetrics
        .filter((m) => m.name === "gpu_engine_usage" && m.tags?.gpu_id)
        .map((m) => m.tags!.gpu_id!),
    ),
  ).sort();

  // MOCK: Add mock GPU IDs if less than 3
  if (availableGpuIds.length < 3) {
    availableGpuIds = ["0", "1", "2"];
  }

  // Get detailed metrics for all GPUs
  const gpuDetailedMetrics = useAppSelector((state) => {
    const gpus: Record<string, ReturnType<typeof selectGpuMetrics>> = {};
    availableGpuIds.forEach((gpuId) => {
      gpus[gpuId] = selectGpuMetrics(state, gpuId);
    });
    return gpus;
  });

  // MOCK: Generate mock data for GPU 1 and 2 if they don't have real data
  const gpu0 = gpuDetailedMetrics["0"];
  if (gpu0) {
    // Mock GPU 1
    if (
      !gpuDetailedMetrics["1"]?.compute ||
      gpuDetailedMetrics["1"].compute === 0
    ) {
      gpuDetailedMetrics["1"] = {
        compute: Math.max((gpu0.compute ?? 0) * 0.6 + Math.random() * 15, 20),
        render: Math.max((gpu0.render ?? 0) * 0.8 + Math.random() * 10, 15),
        copy: Math.max((gpu0.copy ?? 0) * 0.7 + Math.random() * 8, 10),
        video: Math.max((gpu0.video ?? 0) * 0.5 + Math.random() * 8, 10),
        videoEnhance: Math.max(
          (gpu0.videoEnhance ?? 0) * 0.4 + Math.random() * 5,
          5,
        ),
        frequency: Math.max(
          (gpu0.frequency ?? 0) * 0.95 + Math.random() * 0.1,
          0.5,
        ),
        gpuPower: Math.max((gpu0.gpuPower ?? 0) * 0.9 + Math.random() * 5, 1),
        pkgPower: Math.max((gpu0.pkgPower ?? 0) * 0.95 + Math.random() * 2, 5),
      };
    }

    // Mock GPU 2
    if (
      !gpuDetailedMetrics["2"]?.compute ||
      gpuDetailedMetrics["2"].compute === 0
    ) {
      gpuDetailedMetrics["2"] = {
        compute: Math.max((gpu0.compute ?? 0) * 0.75 + Math.random() * 12, 25),
        render: Math.max((gpu0.render ?? 0) * 0.65 + Math.random() * 15, 18),
        copy: Math.max((gpu0.copy ?? 0) * 0.55 + Math.random() * 10, 12),
        video: Math.max((gpu0.video ?? 0) * 0.45 + Math.random() * 12, 8),
        videoEnhance: Math.max(
          (gpu0.videoEnhance ?? 0) * 0.35 + Math.random() * 8,
          6,
        ),
        frequency: Math.max(
          (gpu0.frequency ?? 0) * 0.92 + Math.random() * 0.15,
          0.6,
        ),
        gpuPower: Math.max((gpu0.gpuPower ?? 0) * 0.85 + Math.random() * 7, 2),
        pkgPower: Math.max((gpu0.pkgPower ?? 0) * 0.88 + Math.random() * 4, 6),
      };
    }
  }

  return {
    fps: fps ?? 0,
    cpu: cpu ?? 0,
    cpuDetailed,
    memory: memory ?? 0,
    availableGpuIds,
    gpuDetailedMetrics,
  };
};
