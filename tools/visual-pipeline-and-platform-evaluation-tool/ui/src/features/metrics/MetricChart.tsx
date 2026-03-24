import { useMemo } from "react";
import { useTheme } from "next-themes";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";

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
  maxDataPoints = 60,
  isSummary = false,
  hideSummaryBorder = false,
  forceDark = false,
  useDemoStyles = false,
  wrapLegend = false,
}: MetricChartProps) => {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark" || forceDark;
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

    if (seconds >= 60) {
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = seconds % 60;
      return `${minutes}m ${remainingSeconds}s`;
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
  const summaryBorderClassName = isDarkTheme
    ? "border-2 border-energy-blue/40 shadow-energy-blue/20 ring-1 ring-energy-blue/20"
    : "border-2 border-classic-blue/40 shadow-classic-blue/20 ring-1 ring-classic-blue/20";
  const summaryTitleClassName = isDarkTheme
    ? "text-energy-blue-tint-1"
    : "text-classic-blue";

  return (
    <div
      className={`${
        useDemoStyles
          ? `${forceDark ? "bg-neutral-950/50" : "bg-card/80"}`
          : "bg-background"
      } ${useDemoStyles ? "rounded-xl shadow-2xl" : "shadow-md"} ${isCompact ? "p-4 pb-6" : "p-4"} max-w-full ${isCompact ? "overflow-visible" : "overflow-hidden"} ${
        isSummary && !hideSummaryBorder
          ? summaryBorderClassName
          : useDemoStyles
            ? forceDark
              ? "border border-neutral-800/50"
              : "border border-border"
            : ""
      } ${className}`}
    >
      {hasTitle && (
        <h3
          className={`${
            useDemoStyles
              ? `text-[10px] font-semibold uppercase tracking-widest ${isCompact ? "mb-6" : "mb-10"} ${
                  isSummary && !hideSummaryBorder
                    ? summaryTitleClassName
                    : "text-neutral-400"
                }`
              : "text-sm font-medium text-foreground mb-5"
          }`}
        >
          {title}
        </h3>
      )}
      <div className="relative">
        <ChartContainer
          config={chartConfig}
          className={
            isCompact
              ? "h-[80px] w-full"
              : useDemoStyles
                ? "h-[250px] w-full"
                : "h-[230px] w-full"
          }
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
                  className={
                    useDemoStyles
                      ? forceDark
                        ? "bg-neutral-900 border-neutral-700 text-white"
                        : "bg-popover border-border text-popover-foreground"
                      : "bg-neutral-900 border-neutral-700 text-white"
                  }
                  labelFormatter={(value) => {
                    if (!value) return "";
                    const seconds = parseInt(value as string);
                    return `Time: ${formatTime(seconds)}`;
                  }}
                  formatter={(value, name) => {
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
                    className={`${useDemoStyles ? (forceDark ? "text-white" : "text-foreground") : "text-foreground"} text-[8px] ${wrapLegend ? "flex-wrap gap-x-3 gap-y-1" : ""}`}
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
          className={`absolute right-0 pb-2 ${showLegend ? "bottom-[30px]" : isCompact ? "bottom-[-8px]" : "bottom-0"}`}
        >
          <span className="text-xs text-neutral-500 font-semibold">
            {totalTime}
          </span>
        </div>
      </div>
    </div>
  );
};
