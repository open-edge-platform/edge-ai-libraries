import { useMetrics } from "@/features/metrics/useMetrics";
import {
  Progress,
  ProgressIndicator,
  ProgressLabel,
  ProgressTrack,
  ProgressValue,
} from "@/components/ui/progress";
import { Cpu } from "lucide-react";
import { useAppSelector } from "@/store/hooks.ts";
import { selectDeviceByFamily } from "@/store/reducers/devices.ts";

export const CpuUsageProgress = () => {
  const { cpu } = useMetrics();
  const deviceName = useAppSelector((state) =>
    selectDeviceByFamily(state, "CPU"),
  );

  return (
    <Progress value={cpu} max={100}>
      <>
        <div className="flex items-center justify-between">
          <ProgressLabel>
            <span className="flex items-center gap-2">
              <Cpu className="h-4 w-4" />
              CPU: {deviceName?.full_device_name}
            </span>
          </ProgressLabel>
          <ProgressValue>
            {(_, value) => `${value?.toFixed(2) ?? 0}%`}
          </ProgressValue>
        </div>
        <ProgressTrack>
          <ProgressIndicator />
        </ProgressTrack>
      </>
    </Progress>
  );
};
