import { Cpu, Gauge, Gpu } from "lucide-react";
import { useMetrics } from "@/features/metrics/useMetrics.ts";
import { useConnectionStatus } from "@/features/metrics/useConnectionStatus.ts";

interface FpsDisplayProps {
  className?: string;
}

const FpsDisplay = ({ className = "" }: FpsDisplayProps) => {
  const { fps, cpu, gpu } = useMetrics();
  const { isConnected, statusColor, statusIcon } = useConnectionStatus();

  return (
    <div
      className={`bg-white text-black/80 p-2 shadow-lg text-sm ${className}`}
    >
      <div className="flex flex-row gap-2 font-mono justify-center items-center">
        <span className={statusColor}>{statusIcon}</span>
        {isConnected ? (
          <>
            <Gauge />
            {fps}
            <Cpu />
            {cpu.toFixed(2)}%
            <Gpu />
            {gpu.toFixed(2)}%
          </>
        ) : (
          "No connection"
        )}
      </div>
    </div>
  );
};

export default FpsDisplay;
