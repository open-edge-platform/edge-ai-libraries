import { useMetrics } from "@/features/metrics/useMetrics";
import {
  Progress,
  ProgressIndicator,
  ProgressLabel,
  ProgressTrack,
  ProgressValue,
} from "@/components/ui/progress";
import { Gpu } from "lucide-react";
import { useAppSelector } from "@/store/hooks.ts";
import { selectDeviceByName } from "@/store/reducers/devices.ts";

export const Gpu1UsageProgress = () => {
  const { gpu1 } = useMetrics();
  const deviceName = useAppSelector((state) =>
    selectDeviceByName(state, "GPU.1"),
  );

  return (
    <Progress value={gpu1} max={100}>
      <>
        <div className="flex items-center justify-between">
          <ProgressLabel>
            <span className="flex items-center gap-2">
              <Gpu className="h-4 w-4" />
              GPU: {deviceName?.full_device_name}
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
