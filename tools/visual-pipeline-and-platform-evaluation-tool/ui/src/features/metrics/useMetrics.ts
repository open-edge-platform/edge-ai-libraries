import { useAppSelector } from "@/store/hooks.ts";
import {
  selectCpuMetric,
  selectFpsMetric,
  selectGpuMetric,
  selectAllGpuMetrics,
} from "@/store/reducers/metrics.ts";

export const useMetrics = () => {
  const fps = useAppSelector(selectFpsMetric);
  const cpu = useAppSelector(selectCpuMetric);
  const gpu = useAppSelector(selectGpuMetric);
  const gpus = useAppSelector(selectAllGpuMetrics);

  return {
    fps: fps ?? 0,
    cpu: cpu ?? 0,
    gpu: gpu ?? 0,
    gpus: gpus ?? [],
    npu: 0,
  };
};
