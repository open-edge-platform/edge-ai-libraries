import { GpuMetricCard } from "./GpuMetricCard"
import { MetricCard } from "./MetricCard"
import classes from "./MetricsPanel.module.scss"
import { GPU_ENGINES, GpuEngine, MetricsPoint, useMetricsStream } from "./UseMetricsStream"

const getNumericData = (
  points: MetricsPoint[],
  key: "cpu" | "npu" | "ram"
) => points.map((p) => p[key]).filter((v): v is number => typeof v === "number")

const getGpuEngineData = (points: MetricsPoint[], engine: GpuEngine) =>
  points.map((point) => point.gpu[engine]).filter((value): value is number => typeof value === "number")

const latestValue = (
  points: MetricsPoint[],
  key: "cpu" | "npu" | "ram"
) => {
  const value = points.at(-1)?.[key]
  return typeof value === "number" ? `${value.toFixed(1)}%` : "N/A"
}

export function MetricsPanel() {
  const { points, isConnected } = useMetricsStream("percent")

  const metrics = [
    {
      label: "CPU",
      color: "#00A3F6",
      data: getNumericData(points, "cpu"),
      value: latestValue(points, "cpu"),
    },
    {
      label: "NPU",
      color: "#62CE58",
      data: getNumericData(points, "npu"),
      value: latestValue(points, "npu"),
    },
    {
      label: "RAM",
      color: "#F3AD26",
      data: getNumericData(points, "ram"),
      value: latestValue(points, "ram"),
    },
  ]

  const gpuColors: Record<GpuEngine, string> = {
    bcs: "#C442CF",
    rcs: "#00A3F6",
    ccs: "#62CE58",
    vcs: "#F3AD26",
    vecs: "#E42222",
  }

  const gpuEngineSeries = GPU_ENGINES.map((engine) => ({
    label: engine,
    color: gpuColors[engine],
    data: getGpuEngineData(points, engine),
  }))

  return (
    <section className={classes.chartsPanel}>
      <div className={classes.chartsHeader}>
        <div className={isConnected ? classes.liveDot : classes.offlineDot} />
        <span className={classes.chartsTitle}>Live system metrics</span>
      </div>

      <div className={classes.chartsGrid}>
        {metrics.map((metric) => (
          <MetricCard
            key={metric.label}
            label={metric.label}
            value={metric.value}
            color={metric.color}
            data={metric.data}
          />
        ))}

        <GpuMetricCard series={gpuEngineSeries} />
      </div>
    </section>
  )
}
