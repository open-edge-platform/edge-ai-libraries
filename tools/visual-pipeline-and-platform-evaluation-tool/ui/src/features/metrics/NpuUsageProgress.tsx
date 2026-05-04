import {
  Progress,
  ProgressIndicator,
  ProgressLabel,
  ProgressTrack,
  ProgressValue,
} from "@/components/ui/progress";
import { Gpu } from "lucide-react";
import { useAppSelector } from "@/store/hooks.ts";
import { selectDeviceByFamily } from "@/store/reducers/devices.ts";
import { formatDeviceName } from "@/lib/utils";

export const NpuUsageProgress = () => {
  const deviceName = useAppSelector((state) =>
    selectDeviceByFamily(state, "NPU"),
  );
  return (
    <Progress value={0} max={100}>
      <>
        <div className="flex items-center justify-between">
          <ProgressLabel>
            <span className="flex items-center gap-2">
              <Gpu className="h-4 w-4" />
              NPU: {formatDeviceName(deviceName?.full_device_name)} (metrics coming soon)
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
