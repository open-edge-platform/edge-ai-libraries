import { MetricCard } from "./MetricCard"
import classes from "./MetricsPanel.module.scss"

const makePoints = (base: number, noise: number) =>
    Array.from({ length: 20 }, (_, i) =>
        Math.min(
            99,
            Math.max(5, base + Math.sin(i * 0.7) * noise + (Math.random() - 0.5) * noise * 0.8)
        )
    ).map(Math.round)

const metrics = [
    { label: "CPU", color: "#00A3F6", base: 67, noise: 18 },
    { label: "NPU", color: "#C442CF", base: 43, noise: 14 },
    { label: "RAM", color: "#F3AD26", base: 78, noise: 8 },
    { label: "GPU", color: "#62CE58", base: 94, noise: 5 },
]

export function MetricsPanel() {
    return (
        <section className={classes.chartsPanel}>
            <div className={classes.chartsHeader}>
                <div className={classes.liveDot} />
                <span className={classes.chartsTitle}>Live system metrics</span>
            </div>

            <div className={classes.chartsGrid}>
                {metrics.map((metric) => {
                    const data = makePoints(metric.base, metric.noise)
                    const value = data[data.length - 1]

                    return (
                        <MetricCard
                            key={metric.label}
                            label={metric.label}
                            value={value}
                            color={metric.color}
                            data={data}
                        />
                    )
                })}
            </div>
        </section>
    )
}