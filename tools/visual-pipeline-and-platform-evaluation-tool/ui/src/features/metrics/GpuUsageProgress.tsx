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
import { selectGpuDevices } from "@/store/reducers/devices.ts";

export const GpuUsageProgress = () => {
  const { gpus } = useMetrics();
  const gpuDevices = useAppSelector(selectGpuDevices);

  const deviceMap = new Map(
    gpuDevices.map((device) => {
      // Handle both single card "GPU" and multiple cards "GPU.0", "GPU.1"
      const id =
        device.device_name === "GPU"
          ? "0"
          : device.device_name.replace("GPU.", "");
      return [id, device];
    }),
  );

  return (
    <>
      {gpus.map((gpu) => {
        const device = deviceMap.get(gpu.id);
        const deviceLabel = device?.device_name || `GPU.${gpu.id}`;
        const deviceFullName = device?.full_device_name || "Unknown GPU";

        return (
          <Progress key={gpu.id} value={gpu.usage} max={100}>
            <>
              <div className="flex items-center justify-between">
                <ProgressLabel>
                  <span className="flex items-center gap-2">
                    <Gpu className="h-4 w-4 shrink-0" />
                    {deviceLabel}: {deviceFullName}
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
      })}
    </>
  );
};
