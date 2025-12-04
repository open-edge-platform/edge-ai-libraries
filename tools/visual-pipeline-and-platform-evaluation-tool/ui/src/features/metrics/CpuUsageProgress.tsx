import { useMetrics } from "@/features/metrics/useMetrics";
import {
  Progress,
  ProgressIndicator,
  ProgressLabel,
  ProgressTrack,
  ProgressValue,
} from "@/components/ui/progress";
import { Cpu } from "lucide-react";

export const CpuUsageProgress = () => {
  const { cpu } = useMetrics();

  return (
    <Progress value={cpu} max={100}>
      <>
        <div className="flex items-center justify-between">
          <ProgressLabel>
            <span className="flex items-center gap-2">
              <Cpu className="h-4 w-4" />
              CPU
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
