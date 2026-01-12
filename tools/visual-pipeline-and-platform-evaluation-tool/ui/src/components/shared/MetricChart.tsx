import { useMemo } from "react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import {
  type ChartConfig,
  ChartContainer,
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
}

export const MetricChart = ({
  title,
  data,
  dataKeys,
  colors,
  unit,
  className = "",
  yAxisDomain = [0, 100],
}: MetricChartProps) => {
  const chartConfig = useMemo(() => {
    const config: ChartConfig = {};
    dataKeys.forEach((key, index) => {
      config[key] = {
        label: key.charAt(0).toUpperCase() + key.slice(1),
        color: colors[index] || `hsl(${index * 60}, 70%, 50%)`,
      };
    });
    return config;
  }, [dataKeys, colors]);

  const formattedData = useMemo(() => {
    return data.map((point) => ({
      ...point,
      time: new Date(point.timestamp).toLocaleTimeString("pl-PL", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
    }));
  }, [data]);

  return (
    <div className={`bg-white rounded-lg shadow-md p-4 ${className}`}>
      <h3 className="text-sm font-medium text-gray-900 mb-3">{title}</h3>
      <ChartContainer config={chartConfig} className="h-[200px] w-full">
        <AreaChart data={formattedData}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="time"
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            tickFormatter={(value) => value.slice(0, 5)}
            minTickGap={40}
            interval="preserveStartEnd"
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            domain={yAxisDomain}
            tickFormatter={(value) => `${value}${unit}`}
          />
          <ChartTooltip
            content={
              <ChartTooltipContent
                labelFormatter={(value) => `Czas: ${value}`}
                formatter={(value) => `${Number(value).toFixed(2)}${unit}`}
              />
            }
          />
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
    </div>
  );
};
