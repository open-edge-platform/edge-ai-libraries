import { useMemo, useState } from "react";
import { Cpu, Gauge, Gpu } from "lucide-react";
import { useMetrics } from "@/features/metrics/useMetrics.ts";
import { useMetricHistory } from "@/hooks/useMetricHistory.ts";
import { MetricChart } from "@/components/shared/MetricChart.tsx";
import { GpuSelector } from "@/components/shared/GpuSelector.tsx";

interface MetricCardProps {
  title: string;
  value: number;
  unit: string;
  icon: React.ReactNode;
}

const MetricCard = ({ title, value, unit, icon }: MetricCardProps) => (
  <div className="bg-white shadow-md p-4 flex items-center space-x-3">
    <div className="shrink-0 p-2 bg-classic-blue/5 dark:bg-blue-steel-shade-1">
      {icon}
    </div>
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
  const { fps, cpu, gpu, gpu1 } = useMetrics();
  const history = useMetricHistory();
  const [selectedGpu, setSelectedGpu] = useState<number>(0);

  // MOCK
  const availableGpus = [0, 1, 2];

  const fpsData = useMemo(
    () =>
      history.map((point) => ({
        timestamp: point.timestamp,
        value: point.fps ?? 0,
      })),
    [history]
  );

  const cpuData = useMemo(
    () =>
      history.map((point) => ({
        timestamp: point.timestamp,
        user: point.cpuUser ?? 0,
        system: point.cpuSystem ?? 0,
      })),
    [history]
  );

  const gpuData = useMemo(() => {
    if (selectedGpu === 0) {
      return history.map((point) => ({
        timestamp: point.timestamp,
        compute: point.gpu0Compute ?? 0,
        render: point.gpu0Render ?? 0,
        video: point.gpu0Video ?? 0,
      }));
    } else {
      return history.map((point) => ({
        timestamp: point.timestamp,
        compute: point.gpu1Compute ?? 0,
        render: point.gpu1Render ?? 0,
        video: point.gpu1Video ?? 0,
      }));
    }
  }, [history, selectedGpu]);

  return (
    <div className={`space-y-4 ${className}`}>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
        <div className="space-y-4">
          <MetricCard
            title="Frame Rate"
            value={fps}
            unit="fps"
            icon={<Gauge className="h-6 w-6 text-magenta-chart" />}
          />
          <MetricChart
            title="Frame Rate Over Time"
            data={fpsData}
            dataKeys={["value"]}
            colors={["var(--color-magenta-chart)"]}
            unit=" fps"
            yAxisDomain={[0, Math.max(...fpsData.map((d) => d.value), 60)]}
          />
        </div>

        <div className="space-y-4">
          <MetricCard
            title="CPU Usage"
            value={cpu}
            unit="%"
            icon={<Cpu className="h-6 w-6 text-green-chart" />}
          />
          <MetricChart
            title="CPU Usage Over Time"
            data={cpuData}
            dataKeys={["user", "system"]}
            colors={["var(--color-green-chart)", "var(--color-red-chart)"]}
            unit="%"
            yAxisDomain={[0, 100]}
          />
        </div>

        <div className="space-y-4">
          <MetricCard
            title="GPU Usage"
            value={selectedGpu === 0 ? gpu : (gpu1 ?? 0)}
            unit="%"
            icon={<Gpu className="h-6 w-6 text-purple-600" />}
          />
          <div className="bg-white shadow-md p-4">
            <h3 className="text-sm font-medium text-gray-900 mb-3">
              GPU {selectedGpu} Usage Over Time
            </h3>
            <div className="flex gap-4 items-stretch -mt-3">
              <div className="flex">
                <GpuSelector
                  availableGpus={availableGpus}
                  selectedGpu={selectedGpu}
                  onGpuChange={setSelectedGpu}
                />
              </div>
              <div className="flex-1">
                <MetricChart
                  title=""
                  data={gpuData}
                  dataKeys={["compute", "render", "video"]}
                  colors={[
                    "var(--color-purple-chart)",
                    "var(--color-yellow-chart)",
                    "var(--color-orange-chart)",
                  ]}
                  unit="%"
                  yAxisDomain={[0, 100]}
                  className="!shadow-none !p-0"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
