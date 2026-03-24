/*SPDX-License-Identifier: Apache-2.0*/

export interface MetricCardProps {
  title: string;
  value: number;
  unit: string;
  icon: React.ReactNode;
  isSummary?: boolean;
  forceDark?: boolean;
  useDemoStyles?: boolean;
  summaryCardClassName?: string;
  summaryIconClassName?: string;
  summaryTitleClassName?: string;
  summaryUnitClassName?: string;
}

export const MetricCard = ({
  title,
  value,
  unit,
  icon,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
  summaryCardClassName = "border-2 border-energy-blue/60 shadow-energy-blue/20 shadow-lg ring-2 ring-energy-blue/30",
  summaryIconClassName = "bg-gradient-to-br from-energy-blue/20 to-energy-blue-tint-1/20",
  summaryTitleClassName = "text-energy-blue-tint-1",
  summaryUnitClassName = "text-energy-blue-tint-2",
}: MetricCardProps) => (
  <div
    className={`${
      useDemoStyles
        ? `${forceDark ? "bg-neutral-950/50" : "bg-card/80"}`
        : "bg-background"
    } ${useDemoStyles ? "rounded-xl shadow-2xl p-6" : "shadow-md p-4"} flex items-center space-x-3 transition-all ${
      isSummary
        ? summaryCardClassName
        : useDemoStyles
          ? forceDark
            ? "border border-neutral-800/50"
            : "border border-border"
          : ""
    }`}
  >
    <div
      className={`shrink-0 p-3 rounded-lg backdrop-blur-sm ${
        useDemoStyles
          ? isSummary
            ? summaryIconClassName
            : "bg-gradient-to-br from-white/10 to-white/5"
          : "bg-classic-blue/5 dark:bg-teal-chart p-2 rounded-none"
      }`}
    >
      {icon}
    </div>
    <div className={useDemoStyles ? "flex-1" : undefined}>
      <h3
        className={`${
          useDemoStyles
            ? `text-[11px] font-semibold uppercase tracking-widest mb-3 ${
                isSummary ? summaryTitleClassName : "text-neutral-400"
              }`
            : "text-sm font-medium text-foreground mb-2"
        }`}
      >
        {title}
      </h3>
      <p
        className={`text-3xl font-bold ${
          useDemoStyles && forceDark ? "text-white" : "text-foreground"
        }`}
      >
        {value.toFixed(2)}
        <span
          className={`text-sm ml-1.5 font-semibold ${
            isSummary ? summaryUnitClassName : "text-muted-foreground"
          }`}
        >
          {unit}
        </span>
      </p>
    </div>
  </div>
);
