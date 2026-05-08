import { MetricCard } from "./MetricCard"
import classes from "./MetricsPanel.module.scss"
import { useMetricsStream, MetricsPoint } from "./UseMetricsStream"

const getNumericData = (
  points: MetricsPoint[],
  key: "cpu" | "gpu" | "npu" | "ram"
) => points.map((p) => p[key]).filter((v): v is number => typeof v === "number")

const latestValue = (
  points: MetricsPoint[],
  key: "cpu" | "gpu" | "npu" | "ram"
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
      color: "#C442CF",
      data: getNumericData(points, "npu"),
      value: latestValue(points, "npu"),
    },
    {
      label: "RAM",
      color: "#F3AD26",
      data: getNumericData(points, "ram"),
      value: latestValue(points, "ram"),
    },
    {
      label: "GPU",
      color: "#62CE58",
      data: getNumericData(points, "gpu"),
      value: latestValue(points, "gpu"),
    },
  ]

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
      </div>
    </section>
  )
}