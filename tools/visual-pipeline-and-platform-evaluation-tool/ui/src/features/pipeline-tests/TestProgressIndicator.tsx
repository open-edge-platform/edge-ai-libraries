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
  const { fps, cpu, gpu, gpu1 } = useMetrics();
  const history = useMetricHistory();
  const [selectedGpu, setSelectedGpu] = useState<0 | 1>(0);

  const hasGpu1 = gpu1 > 0;

  // Dane dla wykresu FPS
  const fpsData = useMemo(
    () =>
      history.map((point) => ({
        timestamp: point.timestamp,
        value: point.fps ?? 0,
      })),
    [history]
  );

  // Dane dla wykresu CPU
  const cpuData = useMemo(
    () =>
      history.map((point) => ({
        timestamp: point.timestamp,
        value: point.cpu ?? 0,
      })),
    [history]
  );

  // Dane dla wykresu GPU - może pokazywać wiele metryk
  const gpuData = useMemo(() => {
    if (hasGpu1) {
      // Jeśli mamy dwa GPU, pokaż wybrane albo oba
      return history.map((point) => ({
        timestamp: point.timestamp,
        gpu0: point.gpu ?? 0,
        gpu1: point.gpu1 ?? 0,
      }));
    } else {
      // Jeśli tylko jedno GPU
      return history.map((point) => ({
        timestamp: point.timestamp,
        value: point.gpu ?? 0,
      }));
    }
  }, [history, hasGpu1]);

  return (
    <div className={`space-y-4 ${className}`}>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
        {/* Kolumna FPS */}
        <div className="space-y-4">
          <MetricCard
            title="Frame Rate"
            value={fps}
            unit="fps"
            icon={<Gauge className="h-6 w-6 text-blue-600" />}
          />
          <MetricChart
            title="Frame Rate Over Time"
            data={fpsData}
            dataKeys={["value"]}
            colors={["hsl(217, 91%, 60%)"]}
            unit=" fps"
            yAxisDomain={[0, Math.max(...fpsData.map((d) => d.value), 60)]}
          />
        </div>

        {/* Kolumna CPU */}
        <div className="space-y-4">
          <MetricCard
            title="CPU Usage"
            value={cpu}
            unit="%"
            icon={<Cpu className="h-6 w-6 text-green-600" />}
          />
          <MetricChart
            title="CPU Usage Over Time"
            data={cpuData}
            dataKeys={["value"]}
            colors={["hsl(142, 71%, 45%)"]}
            unit="%"
            yAxisDomain={[0, 100]}
          />
        </div>

        {/* Kolumna GPU */}
        <div className="space-y-4">
          <MetricCard
            title="GPU Usage"
            value={selectedGpu === 0 ? gpu : gpu1}
            unit="%"
            icon={<Gpu className="h-6 w-6 text-purple-600" />}
          />
          <div>
            <GpuSelector
              hasGpu1={hasGpu1}
              selectedGpu={selectedGpu}
              onGpuChange={setSelectedGpu}
            />
            {hasGpu1 ? (
              <MetricChart
                title="GPU Usage Over Time"
                data={gpuData}
                dataKeys={["gpu0", "gpu1"]}
                colors={["hsl(271, 81%, 56%)", "hsl(280, 65%, 60%)"]}
                unit="%"
                yAxisDomain={[0, 100]}
              />
            ) : (
              <MetricChart
                title="GPU Usage Over Time"
                data={gpuData}
                dataKeys={["value"]}
                colors={["hsl(271, 81%, 56%)"]}
                unit="%"
                yAxisDomain={[0, 100]}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
