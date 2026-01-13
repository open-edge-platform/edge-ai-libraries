import { useAppSelector } from "@/store/hooks.ts";
import {
  selectCpuMetric,
  selectCpuMetrics,
  selectFpsMetric,
  selectGpu1Metric,
  selectGpuMetric,
  selectGpuMetrics,
} from "@/store/reducers/metrics.ts";

export const useMetrics = () => {
  const fps = useAppSelector(selectFpsMetric);
  const cpu = useAppSelector(selectCpuMetric);
  const cpuDetailed = useAppSelector(selectCpuMetrics);
  const gpu = useAppSelector(selectGpuMetric);
  const gpu1 = useAppSelector(selectGpu1Metric);
  const gpu0Detailed = useAppSelector((state) => selectGpuMetrics(state, "0"));
  const gpu1Detailed = useAppSelector((state) => selectGpuMetrics(state, "1"));

  // MOCK: Symuluj drugie GPU dla testów
  const mockGpu1 =
    gpu1 === 0 ? Math.max(gpu * 0.7 + Math.random() * 10, 30) : gpu1;
  const mockGpu1Detailed = {
    compute:
      gpu1Detailed.compute === 0
        ? Math.max(gpu0Detailed.compute * 0.6 + Math.random() * 15, 20)
        : gpu1Detailed.compute,
    render:
      gpu1Detailed.render === 0
        ? Math.max(gpu0Detailed.render * 0.8 + Math.random() * 10, 15)
        : gpu1Detailed.render,
    video:
      gpu1Detailed.video === 0
        ? Math.max(gpu0Detailed.video * 0.5 + Math.random() * 8, 10)
        : gpu1Detailed.video,
    videoEnhance:
      gpu1Detailed.videoEnhance === 0
        ? Math.max(gpu0Detailed.videoEnhance * 0.4 + Math.random() * 5, 5)
        : gpu1Detailed.videoEnhance,
  };

  return {
    fps: fps ?? 0,
    cpu: cpu ?? 0,
    cpuDetailed,
    gpu: gpu ?? 0,
    gpu1: mockGpu1, // Użyj mock wartości
    gpu0Detailed,
    gpu1Detailed: mockGpu1Detailed, // Użyj mock wartości
    npu: 0,
  };
};
