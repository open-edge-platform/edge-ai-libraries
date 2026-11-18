/** Formatting and delta helpers shared by every comparison view. */

export type MetricDirection = "higher-is-better" | "lower-is-better";

type MetricMeta = {
  label: string;
  unit?: string;
  digits: number;
  direction: MetricDirection;
};

const METRICS: Record<string, MetricMeta> = {
  total_fps: { label: "Total FPS", digits: 2, direction: "higher-is-better" },
  per_stream_fps: {
    label: "Per-stream FPS",
    digits: 2,
    direction: "higher-is-better",
  },
  total_streams: { label: "Streams", digits: 0, direction: "higher-is-better" },
  latency_avg_ms: {
    label: "Avg latency",
    unit: "ms",
    digits: 1,
    direction: "lower-is-better",
  },
  latency_min_ms: {
    label: "Min latency",
    unit: "ms",
    digits: 1,
    direction: "lower-is-better",
  },
  latency_max_ms: {
    label: "Max latency",
    unit: "ms",
    digits: 1,
    direction: "lower-is-better",
  },
  cpu_usage: {
    label: "CPU",
    unit: "%",
    digits: 1,
    direction: "lower-is-better",
  },
  gpu_usage: {
    label: "GPU",
    unit: "%",
    digits: 1,
    direction: "lower-is-better",
  },
  npu_usage: {
    label: "NPU",
    unit: "%",
    digits: 1,
    direction: "lower-is-better",
  },
  media_usage: {
    label: "Media",
    unit: "%",
    digits: 1,
    direction: "lower-is-better",
  },
  memory_usage: {
    label: "Memory",
    unit: "%",
    digits: 1,
    direction: "lower-is-better",
  },
  power_usage: {
    label: "Power",
    unit: "W",
    digits: 2,
    direction: "lower-is-better",
  },
  score_total: {
    label: "Overall score",
    digits: 2,
    direction: "higher-is-better",
  },
  score_performance: {
    label: "Perf score",
    digits: 2,
    direction: "higher-is-better",
  },
  score_efficiency: {
    label: "Efficiency score",
    digits: 2,
    direction: "higher-is-better",
  },
  pass_rate: {
    label: "Pass rate",
    unit: "%",
    digits: 1,
    direction: "higher-is-better",
  },
  fps_floor: { label: "FPS floor", digits: 0, direction: "higher-is-better" },
  elapsed_time: { label: "Duration", digits: 0, direction: "lower-is-better" },
  execution_time: {
    label: "Duration",
    digits: 0,
    direction: "lower-is-better",
  },
};

export const metricLabel = (metric: string) =>
  METRICS[metric]?.label ??
  metric.replace(/_/g, " ").replace(/^\w/, c => c.toUpperCase());

export const metricUnit = (metric: string) => METRICS[metric]?.unit ?? "";

export const metricDirection = (metric: string): MetricDirection =>
  METRICS[metric]?.direction ?? "higher-is-better";

export const isDurationMetric = (metric: string) =>
  metric === "elapsed_time" || metric === "execution_time";

export const toNumber = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

export const formatDuration = (milliseconds: number) => {
  const seconds = Math.round(milliseconds / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
};

export const formatMetric = (metric: string, value: unknown): string => {
  const numeric = toNumber(value);
  if (numeric === null) return "–";
  if (isDurationMetric(metric)) return formatDuration(numeric);
  const meta = METRICS[metric];
  return `${numeric.toFixed(meta?.digits ?? 2)}${meta?.unit ?? ""}`;
};

export type Delta = {
  percent: number;
  better: boolean;
};

/** Relative change of `value` against `baseline`, oriented by metric direction. */
export const computeDelta = (
  metric: string,
  value: unknown,
  baseline: unknown
): Delta | null => {
  const current = toNumber(value);
  const reference = toNumber(baseline);
  if (current === null || reference === null || reference === 0) return null;
  const percent = ((current - reference) / Math.abs(reference)) * 100;
  if (Math.abs(percent) < 0.05) return { percent: 0, better: true };
  const better =
    metricDirection(metric) === "higher-is-better" ? percent > 0 : percent < 0;
  return { percent, better };
};

export const formatDelta = (delta: Delta) =>
  `${delta.percent > 0 ? "+" : ""}${delta.percent.toFixed(1)}%`;

export const chartMetricTitle = (metric: string) =>
  `${metricLabel(metric)} by workload`;
