import type {
  BenchmarkWorkload,
  BenchmarkWorkloadRun,
  Pipeline,
} from "@/api/api.generated.ts";
import { BenchmarkWorkloadSummaryChart } from "@/features/benchmarks/BenchmarkWorkloadSummaryChart";

const SUMMARY_CHARTS = [
  {
    title: "Total FPS",
    metricKey: "total_fps",
    formatValue: (value: number) => value.toFixed(2),
    allowDecimals: false,
  },
  {
    title: "Latency",
    metricKey: "latency_avg_ms",
    formatValue: (value: number) => `${value.toFixed(2)} ms`,
    allowDecimals: true,
  },
  {
    title: "Power",
    metricKey: "power_usage",
    formatValue: (value: number) => `${value.toFixed(2)} W`,
    allowDecimals: true,
  },
] as const;

type BenchmarkWorkloadSummaryProps = {
  benchmarkWorkload?: BenchmarkWorkload;
  workloadRun: BenchmarkWorkloadRun;
  pipeline?: Pipeline;
};

export const BenchmarkWorkloadSummary = ({
  benchmarkWorkload,
  workloadRun,
  pipeline,
}: BenchmarkWorkloadSummaryProps) => (
  <div className="grid gap-4 xl:grid-cols-3">
    {SUMMARY_CHARTS.map((chart) => (
      <BenchmarkWorkloadSummaryChart
        key={chart.metricKey}
        benchmarkWorkload={benchmarkWorkload}
        workloadRun={workloadRun}
        pipeline={pipeline}
        title={chart.title}
        metricKey={chart.metricKey}
        formatValue={chart.formatValue}
        allowDecimals={chart.allowDecimals}
      />
    ))}
  </div>
);
