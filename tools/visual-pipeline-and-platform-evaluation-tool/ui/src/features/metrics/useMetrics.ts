import { useAppSelector } from "@/store/hooks.ts";
import {
  selectCpuMetric,
  selectFpsMetric,
  selectAllGpuMetrics,
} from "@/store/reducers/metrics.ts";

export const useMetrics = () => {
  const fps = useAppSelector(selectFpsMetric);
  const cpu = useAppSelector(selectCpuMetric);
  const gpus = useAppSelector(selectAllGpuMetrics);

  return {
    fps: fps ?? 0,
    cpu: cpu ?? 0,
    gpus,
    npu: 0,
  };
};
