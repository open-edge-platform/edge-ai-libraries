import { Activity, Cpu, Gauge, Gpu, Wifi, WifiOff } from "lucide-react";
import { useMetrics } from "@/features/metrics/useMetrics.ts";
import { useConnectionStatus } from "@/features/metrics/useConnectionStatus.ts";

interface MetricCardProps {
  title: string;
  value: number;
  unit: string;
  icon: React.ReactNode;
}

const MetricCard = ({ title, value, unit, icon }: MetricCardProps) => (
  <div className="bg-white rounded-lg shadow-md p-4 flex items-center space-x-3">
    <div className="shrink-0 p-2 bg-blue-100 rounded-lg">{icon}</div>
    <div>
      <h3 className="text-sm font-medium text-gray-900">{title}</h3>
      <p className="text-2xl font-bold text-gray-900">
        {value.toFixed(2)}
        <span className="text-sm text-gray-500 ml-1">{unit}</span>
      </p>
    </div>
  </div>
);

interface MetricsDashboardProps {
  className?: string;
}

export const MetricsDashboard = ({ className = "" }: MetricsDashboardProps) => {
  const { fps, cpu, gpu } = useMetrics();
  const { isConnected, isConnecting, error } = useConnectionStatus();

  return (
    <div className={`space-y-4 ${className}`}>
      <div className="flex items-center space-x-2 p-3 rounded-lg bg-gray-50">
        {isConnected ? (
          <Wifi className="h-5 w-5 text-green-600" />
        ) : (
          <WifiOff className="h-5 w-5 text-red-600" />
        )}
        <span className="text-sm font-medium">
          {isConnected
            ? "Connected"
            : isConnecting
              ? "Connecting..."
              : "Disconnected"}
        </span>
        {error && <span className="text-sm text-red-600">({error})</span>}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard
          title="Frame Rate"
          value={fps}
          unit="fps"
          icon={<Gauge className="h-6 w-6 text-blue-600" />}
        />
        <MetricCard
          title="CPU Usage"
          value={cpu}
          unit="%"
          icon={<Cpu className="h-6 w-6 text-green-600" />}
        />
        <MetricCard
          title="GPU Usage"
          value={gpu}
          unit="%"
          icon={<Gpu className="h-6 w-6 text-purple-600" />}
        />
      </div>

      <div className="flex items-center justify-center space-x-2 text-sm text-gray-500">
        <Activity className="h-4 w-4" />
        <span>Real-time metrics</span>
      </div>
    </div>
  );
};
