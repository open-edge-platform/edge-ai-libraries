import { useTheme } from "next-themes";
import { Clock } from "lucide-react";
import { cn } from "@/lib/utils";

interface LatencySummaryPanelProps {
  avgMs: number;
  minMs: number;
  maxMs: number;
  forceDark?: boolean;
}

export const LatencySummaryPanel = ({
  avgMs,
  minMs,
  maxMs,
  forceDark = false,
}: LatencySummaryPanelProps) => {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark" || forceDark;

  const containerClassName = isDarkTheme
    ? "border-2 border-energy-blue/40 bg-neutral-950/50 shadow-energy-blue/10"
    : "border-2 border-classic-blue/40 bg-card/80 shadow-classic-blue/10";
  const titleClassName = isDarkTheme
    ? "text-energy-blue-tint-1"
    : "text-classic-blue";

  const items = [
    { label: "Avg Latency", value: avgMs, unit: "ms", icon: Clock },
    { label: "Min Latency", value: minMs, unit: "ms", icon: Clock },
    { label: "Max Latency", value: maxMs, unit: "ms", icon: Clock },
  ];

  return (
    <div className={cn("rounded-xl p-4 shadow-lg", containerClassName)}>
      <h3
        className={cn("text-[10px] font-semibold uppercase tracking-widest mb-3", titleClassName)}
      >
        Latency Summary
      </h3>
      <div className="grid grid-cols-2 gap-3">
        {items.map((item) => (
          <div key={item.label} className="flex items-center space-x-2">
            <item.icon className="h-4 w-4 text-orange-chart shrink-0" />
            <div>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide">
                {item.label}
              </p>
              <p
                className={cn("text-lg font-bold", isDarkTheme ? "text-white" : "text-foreground")}
              >
                {item.value.toFixed(2)}
                <span className="text-xs ml-1 text-muted-foreground">
                  {item.unit}
                </span>
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
