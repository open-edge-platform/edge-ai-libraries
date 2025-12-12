import { useAppSelector } from "@/store/hooks.ts";
import {
  selectCpuMetric,
  selectFpsMetric,
  selectGpu1Metric,
  selectGpuMetric,
} from "@/store/reducers/metrics.ts";

export const useMetrics = () => {
  const fps = useAppSelector(selectFpsMetric);
  const cpu = useAppSelector(selectCpuMetric);
  const gpu = useAppSelector(selectGpuMetric);
  const gpu1 = useAppSelector(selectGpu1Metric);

  return {
    fps: fps ?? 0,
    cpu: cpu ?? 0,
    gpu: gpu ?? 0,
    gpu1: gpu1 ?? 0,
    npu: 0,
  };
};
