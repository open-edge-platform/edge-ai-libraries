import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Filler,
    Tooltip,
} from "chart.js"
import { Line } from "react-chartjs-2"

import classes from "./MetricsPanel.module.scss"

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip)

type MetricCardProps = {
    label: string
    value: number
    color: string
    data: number[]
}

export function MetricCard({ label, value, color, data }: MetricCardProps) {
    const chartData = {
        labels: data.map(() => ""),
        datasets: [
            {
                data,
                borderColor: color,
                backgroundColor: `${color}22`,
                borderWidth: 1.5,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
            },
        ],
    }

    const options = {
        responsive: true,
        maintainAspectRatio: false,
        animation: false as const,
        plugins: {
            legend: {
                display: false,
            },
            tooltip: {
                displayColors: false,
                backgroundColor: "#141f45",
                borderColor: "#1b2652",
                borderWidth: 1,
                titleColor: "#8899cc",
                bodyColor: color,
                callbacks: {
                    label: (context: any) => `${Math.round(context.parsed.y)}%`,
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
        <div className={classes.chartCard}>
            <div className={classes.chartCardHead}>
                <span className={classes.chartCardLabel}>{label}</span>
                <span className={classes.chartCardValue} style={{ color }}>
                    {value}%
                </span>
            </div>

            <div className={classes.chartWrap}>
                <Line data={chartData} options={options} />
            </div>
        </div>
    )
}