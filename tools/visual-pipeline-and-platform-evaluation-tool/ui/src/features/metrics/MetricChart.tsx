import { useMemo } from "react";
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

  return (
    <div
      className={`bg-background shadow-md p-4 max-w-full overflow-hidden ${className}`}
    >
      <h3 className="text-sm font-medium text-foreground mb-8">{title}</h3>
      <div className="relative">
        <ChartContainer
          config={chartConfig}
          className={showLegend ? "h-[230px] w-full" : "h-[200px] w-full"}
        >
          <AreaChart data={formattedData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="time"
              tickLine={false}
              axisLine={false}
              tickMargin={9}
              tickFormatter={() => ""}
              minTickGap={40}
              interval="preserveStartEnd"
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              domain={yAxisDomain}
              tickFormatter={(value) => `${value}${unit}`}
              width={80}
              allowDecimals={false}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent
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
            {showLegend && <ChartLegend content={<ChartLegendContent />} />}
            {dataKeys.map((key, index) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                stroke={colors[index]}
                fill={colors[index]}
                fillOpacity={0.2}
                strokeWidth={2}
                isAnimationActive={false}
              />
            ))}
          </AreaChart>
        </ChartContainer>
        <div
          className={`absolute right-0 pb-2 ${showLegend ? "bottom-[30px]" : "bottom-0"}`}
        >
          <span className="text-xs text-muted-foreground">{totalTime}</span>
        </div>
      </div>
      {!showLegend && <div className="h-[30px]" />}
    </div>
  );
};
