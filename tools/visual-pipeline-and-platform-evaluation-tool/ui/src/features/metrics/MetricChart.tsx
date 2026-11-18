import { useMemo } from "react";
import { Info } from "lucide-react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export interface MetricDataPoint {
  timestamp: number;
  value?: number;
  label?: string;
  [key: string]: number | string | undefined;
}

export interface MetricChartProps {
  title: string;
  data: MetricDataPoint[];
  dataKeys: string[];
  colors: string[];
  unit: string;
  className?: string;
  yAxisDomain?: [number, number];
  showLegend?: boolean;
  labels?: string[];
  titleTooltip?: { label: string; description: string }[];
  additionalTooltipMetrics?: { dataKey: string; label: string }[];
  maxDataPoints?: number;
  isSummary?: boolean;
  hideSummaryBorder?: boolean;
  forceDark?: boolean;
  useDemoStyles?: boolean;
  wrapLegend?: boolean;
}

export const MetricChart = ({
  title,
  data,
  dataKeys,
  colors,
  unit,
  className = "",
  yAxisDomain = [0, 100],
  showLegend = true,
  labels,
  titleTooltip,
  additionalTooltipMetrics,
  maxDataPoints = 60,
  isSummary = false,
  hideSummaryBorder = false,
  forceDark = false,
  useDemoStyles = false,
  wrapLegend = false,
}: MetricChartProps) => {
  const chartConfig = useMemo(() => {
    const config: ChartConfig = {};
    dataKeys.forEach((key, index) => {
      config[key] = {
        label:
          labels?.[index] ?? `${key.charAt(0).toUpperCase()}${key.slice(1)}`,
        color: colors[index] ?? `hsl(${index * 60}, 70%, 50%)`,
      };
    });
    return config;
  }, [dataKeys, colors, labels]);

  const formattedData = useMemo(() => {
    const slicedData = data.slice(-maxDataPoints);
    const startTimestamp = slicedData[0]?.timestamp || 0;

    const formatted = slicedData.map((point) => ({
      ...point,
      time:
        point.timestamp > 0
          ? Math.round((point.timestamp - startTimestamp) / 1000).toString()
          : "",
    }));

    const emptyPointsCount = maxDataPoints - formatted.length;
    if (emptyPointsCount > 0) {
      const emptyPoints = Array.from({ length: emptyPointsCount }, () => ({
        timestamp: 0,
        time: "",
        ...Object.fromEntries(dataKeys.map((key) => [key, null])),
      }));
      return [...emptyPoints, ...formatted];
    }

    return formatted;
  }, [data, maxDataPoints, dataKeys]);

  const totalTime = useMemo(() => {
    const lastPoint = data[data.length - 1];
    const firstPoint = data[0];
    if (!lastPoint || !firstPoint) return "0s";

    const seconds = Math.round(
      (lastPoint.timestamp - firstPoint.timestamp) / 1000,
    );

    if (seconds >= 58) {
      return "1m 0s";
    }

    return `${seconds}s`;
  }, [data]);

  const formatTime = (seconds: number) => {
    if (seconds >= 60) {
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = seconds % 60;
      return `${minutes}m ${remainingSeconds}s`;
    }
    return `${seconds}s`;
  };

  const isCompact = className?.includes("!h-");
  const hasTitle = title.trim().length > 0;
  const summaryBorderClassName =
    "border-2 border-brand-accent/40 shadow-brand-accent/20 ring-1 ring-brand-accent/20";
  const summaryTitleClassName = "text-summary-title";

  return (
    <div
      className={cn(
        useDemoStyles
          ? forceDark
            ? "bg-surface-overlay"
            : "bg-card/80"
          : "bg-background",
        useDemoStyles ? "rounded-xl shadow-2xl" : "shadow-md",
        isCompact ? "p-4 pb-6" : "p-4",
        "max-w-full",
        "overflow-visible",
        isSummary && !hideSummaryBorder
          ? summaryBorderClassName
          : useDemoStyles
            ? forceDark
              ? "border border-surface-overlay-border"
              : "border border-border"
            : "",
        className,
      )}
    >
      {hasTitle && (
        <div
          className={cn(
            "flex items-start justify-between gap-2",
            !useDemoStyles && "mb-5",
            useDemoStyles && (isCompact ? "mb-6" : "mb-10"),
          )}
        >
          <h3
            className={cn(
              useDemoStyles
                ? "text-[0.625rem] font-semibold uppercase tracking-widest"
                : "text-sm font-medium text-foreground",
              useDemoStyles &&
                (isSummary && !hideSummaryBorder
                  ? summaryTitleClassName
                  : "text-muted-foreground"),
            )}
          >
            {title}
          </h3>
          {titleTooltip && (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label="About VLM latency metrics"
                  className="shrink-0 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Info className="size-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="top" align="end" className="max-w-sm">
                <div className="space-y-1.5">
                  {titleTooltip.map((metric) => (
                    <p key={metric.label}>
                      <span className="font-semibold">{metric.label}:</span>{" "}
                      {metric.description}
                    </p>
                  ))}
                </div>
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      )}
      <div className="relative">
        <ChartContainer
          config={chartConfig}
          className={cn(
            isCompact
              ? "h-[5rem] w-full"
              : useDemoStyles
                ? "h-[15.625rem] w-full"
                : "h-[14.375rem] w-full",
          )}
        >
          <AreaChart data={formattedData}>
            <CartesianGrid
              strokeDasharray="3 3"
              vertical={false}
              stroke="#404040"
              opacity={0.3}
            />
            <XAxis
              dataKey="time"
              tickLine={false}
              axisLine={false}
              tickMargin={9}
              tickFormatter={() => ""}
              minTickGap={40}
              interval="preserveStartEnd"
              stroke="#737373"
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              domain={yAxisDomain}
              tickFormatter={(value) => `${value}${unit}`}
              width={80}
              allowDecimals={false}
              stroke="#737373"
              tickCount={isCompact ? 3 : undefined}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  className="bg-popover border-border text-popover-foreground w-max max-w-[calc(100vw-2rem)]"
                  labelFormatter={(value) => {
                    if (!value) return "";
                    const seconds = parseInt(value as string);
                    return `Time: ${formatTime(seconds)}`;
                  }}
                  formatter={(value, name, _item, _index, point) => {
                    if (additionalTooltipMetrics?.length) {
                      const metrics = [
                        {
                          dataKey: String(name),
                          label: chartConfig[String(name)]?.label || name,
                          color: colors[dataKeys.indexOf(String(name))],
                          value,
                        },
                        ...additionalTooltipMetrics.map((metric) => ({
                          ...metric,
                          value: point[metric.dataKey],
                        })),
                      ];

                      return (
                        <div className="grid gap-1.5">
                          {metrics.map((metric) => (
                            <div
                              key={metric.dataKey}
                              className="flex min-w-0 items-center justify-between gap-3"
                            >
                              <span className="flex min-w-0 items-center gap-2">
                                <span
                                  aria-hidden="true"
                                  className={cn(
                                    "h-2 w-2 shrink-0",
                                    metric.color
                                      ? "rounded-[0.125rem]"
                                      : "invisible",
                                  )}
                                  style={
                                    metric.color
                                      ? { backgroundColor: metric.color }
                                      : undefined
                                  }
                                />
                                <span className="break-words">
                                  {metric.label}
                                </span>
                              </span>
                              <span className="shrink-0 font-mono font-medium tabular-nums">
                                {Number(metric.value).toFixed(2)} {unit}
                              </span>
                            </div>
                          ))}
                        </div>
                      );
                    }

                    const label = chartConfig[name as string]?.label || name;
                    return `${label}: ${Number(value).toFixed(2)} ${unit}`;
                  }}
                />
              }
            />
            {showLegend && (
              <ChartLegend
                content={
                  <ChartLegendContent
                    className={cn(
                      useDemoStyles
                        ? forceDark
                          ? "text-white"
                          : "text-foreground"
                        : "text-foreground",
                      "text-[0.5rem]",
                      wrapLegend && "flex-wrap gap-x-3 gap-y-1",
                    )}
                  />
                }
              />
            )}
            {dataKeys.map((key, index) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                stroke={colors[index]}
                fill={colors[index]}
                fillOpacity={0.3}
                strokeWidth={2.5}
                isAnimationActive={false}
              />
            ))}
          </AreaChart>
        </ChartContainer>
        <div
          className={cn(
            "absolute right-0 pb-2",
            showLegend
              ? "bottom-[1.875rem]"
              : isCompact
                ? "bottom-[-0.5rem]"
                : "bottom-0",
          )}
        >
          <span className="text-xs text-muted-foreground font-semibold">
            {totalTime}
          </span>
        </div>
      </div>
    </div>
  );
};
