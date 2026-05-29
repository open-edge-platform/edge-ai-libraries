import {
  Chart as ChartJS,
  type ChartOptions,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  type TooltipItem,
} from "chart.js"
import { Line } from "react-chartjs-2"

import classes from "./MetricsPanel.module.scss"

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip)

type GpuSeries = {
  label: string
  color: string
  data: number[]
}

type GpuMetricCardProps = {
  series: GpuSeries[]
}

export function GpuMetricCard({ series }: GpuMetricCardProps) {
  const labels = Array.from(
    { length: Math.max(...series.map(({ data }) => data.length), 0) },
    () => ""
  )

  const chartData = {
    labels,
    datasets: series.map(({ label, color, data }) => ({
      label,
      data,
      borderColor: color,
      borderWidth: 1.5,
      tension: 0.4,
      pointRadius: data.map((_, index) => (index === data.length - 1 ? 2.5 : 0)),
      pointHoverRadius: data.map((_, index) => (index === data.length - 1 ? 3 : 0)),
    })),
  }

  const options: ChartOptions<"line"> = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false as const,
    interaction: {
      mode: "index" as const,
      intersect: false,
    },
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        backgroundColor: "#141f45",
        borderColor: "#1b2652",
        borderWidth: 1,
        titleColor: "#8899cc",
        bodyColor: "#c2d4f0",
        usePointStyle: true,
        padding: { top: 0, right: 8, bottom: 16, left: 8 },
        callbacks: {
          labelColor: (context: TooltipItem<"line">) => {
            const color = (context.dataset.borderColor as string)
            return {
              borderColor: color,
              backgroundColor: color,
              borderWidth: 0,
            }
          },
          labelPointStyle: () => ({
            pointStyle: "line",
            rotation: 0,
          }),
          label: (context: TooltipItem<"line">) => {
            const label = context.dataset.label ?? "GPU"
            const value = context.parsed.y
            return `${label}: ${value == null ? "N/A" : `${Math.round(value)}%`}`
          },
        },
      },
    },
    scales: {
      x: {
        display: false,
      },
      y: {
        display: false,
        min: 0,
        max: 100,
      },
    },
  }

  return (
    <div className={classes.gpuCard}>
      <div className={classes.gpuHeader}>
        <span className={classes.gpuTitle}>GPU engines</span>

        <div className={classes.gpuLegend}>
          {series.map(({ label, color }) => (
            <div className={classes.gpuLegendItem} key={label}>
              <span className={classes.gpuLegendDot} style={{ backgroundColor: color }} />
              <span>{label}</span>
            </div>
          ))}
        </div>
      </div>

      <div className={classes.chartWrap}>
        <Line data={chartData} options={options} />
      </div>
    </div>
  )
}
