import { Cpu, Gauge, Gpu } from "lucide-react";
import { useMetrics } from "@/features/metrics/useMetrics.ts";

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

interface TestProgressIndicatorProps {
  className?: string;
}

export const TestProgressIndicator = ({
  className = "",
}: TestProgressIndicatorProps) => {
  const { fps, cpu, gpu } = useMetrics();

  return (
    <div className={`space-y-4 ${className}`}>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
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
    </div>
  );
};
