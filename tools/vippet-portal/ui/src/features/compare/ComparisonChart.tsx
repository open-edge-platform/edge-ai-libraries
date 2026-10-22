import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  XAxis,
  YAxis,
} from "recharts";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { formatMetric, toNumber } from "@/lib/format";
import type { Comparison } from "@/api/portalApi";

const PALETTE = [
  "var(--chart-1, #0068b5)",
  "var(--chart-2, #00c7fd)",
  "var(--chart-3, #8f5da2)",
  "var(--chart-4, #e96115)",
  "var(--chart-5, #6ec46e)",
  "var(--chart-6, #b24501)",
];

type ComparisonChartProps = {
  comparison: Comparison;
  metric: string;
};

const truncate = (label: string, max = 34) =>
  label.length > max ? `${label.slice(0, max - 1)}…` : label;

export const ComparisonChart = ({
  comparison,
  metric,
}: ComparisonChartProps) => {
  const rows = comparison.rows
    .filter((row) => !row.key.endsWith("::_suite_"))
    .filter((row) =>
      comparison.columns.some(
        (column) => toNumber(row.cells[column.ref]?.[metric]) !== null,
      ),
    );

  if (rows.length === 0 || comparison.columns.length === 0) return null;

  const config: ChartConfig = Object.fromEntries(
    comparison.columns.map((column, index) => [
      column.ref,
      { label: column.instance_name, color: PALETTE[index % PALETTE.length] },
    ]),
  );

  // A single-workload chart names it elsewhere, so the prefix only adds noise.
  const showGroup = new Set(rows.map((row) => row.group ?? "")).size > 1;

  const data = rows.map((row) => ({
    name: truncate(
      showGroup && row.group ? `${row.group} · ${row.label}` : row.label,
    ),
    ...Object.fromEntries(
      comparison.columns.map((column) => [
        column.ref,
        toNumber(row.cells[column.ref]?.[metric]),
      ]),
    ),
  }));

  return (
    <ChartContainer config={config} className="h-[26rem] w-full">
      <BarChart data={data} margin={{ top: 16, right: 8, bottom: 8, left: 8 }}>
        <CartesianGrid vertical={false} />
        <XAxis
          dataKey="name"
          tickLine={false}
          axisLine={false}
          interval={0}
          angle={-35}
          textAnchor="end"
          height={140}
          tick={{ fontSize: 11 }}
        />
        <YAxis tickLine={false} axisLine={false} width={64} />
        <ChartTooltip
          content={
            <ChartTooltipContent
              formatter={(value) => formatMetric(metric, value)}
            />
          }
        />
        <ChartLegend content={<ChartLegendContent />} />
        {comparison.columns.map((column, index) => (
          <Bar
            key={column.ref}
            dataKey={column.ref}
            name={column.instance_name}
            fill={PALETTE[index % PALETTE.length]}
            radius={2}
            maxBarSize={72}
          >
            {comparison.columns.length <= 2 && rows.length <= 16 ? (
              <LabelList
                dataKey={column.ref}
                position="top"
                className="fill-muted-foreground"
                fontSize={10}
                formatter={(value: unknown) => formatMetric(metric, value)}
              />
            ) : null}
          </Bar>
        ))}
      </BarChart>
    </ChartContainer>
  );
};
