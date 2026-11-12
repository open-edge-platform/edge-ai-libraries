import { useMemo } from "react";
import { Cpu } from "lucide-react";

import type { CpuCoreType } from "@/api/api.generated";
import { useAppSelector } from "@/store/hooks";
import { selectCpuTopology } from "@/store/reducers/devices";
import { selectPerCoreCpuUsage } from "@/store/reducers/metrics";

const CORE_TYPE_LABELS: Record<CpuCoreType, string> = {
  P: "P-cores",
  E: "E-cores",
  LPE: "LPE-cores",
  UNIFORM: "Cores",
};

const CORE_TYPE_ORDER: CpuCoreType[] = ["P", "E", "LPE", "UNIFORM"];

/** Live busy percent of every logical CPU, grouped by core type. */
export const CpuCoreUsage = () => {
  const usage = useAppSelector(selectPerCoreCpuUsage);
  const topology = useAppSelector(selectCpuTopology);

  const groups = useMemo(() => {
    const typeOf = new Map(
      (topology?.cores ?? []).map((core) => [core.cpu, core.core_type]),
    );
    return CORE_TYPE_ORDER.map((type) => ({
      type,
      cores: usage.filter(
        (core) => (typeOf.get(core.cpu) ?? "UNIFORM") === type,
      ),
    })).filter((group) => group.cores.length > 0);
  }, [usage, topology]);

  if (usage.length === 0) {
    return null;
  }

  return (
    <div className="border bg-card p-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium">
        <Cpu className="h-4 w-4" />
        CPU usage per core
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-3">
        {groups.map((group) => (
          <div key={group.type}>
            <p className="mb-1 text-xs text-muted-foreground">
              {CORE_TYPE_LABELS[group.type]}
            </p>
            <div className="flex gap-1">
              {group.cores.map((core) => (
                <div
                  key={core.cpu}
                  className="flex w-7 flex-col items-center"
                  title={`CPU ${core.cpu}: ${core.usage.toFixed(1)}%`}
                >
                  <div className="relative h-16 w-4 bg-muted">
                    <div
                      className="absolute bottom-0 w-full bg-brand-accent transition-[height] duration-500"
                      style={{ height: `${core.usage}%` }}
                    />
                  </div>
                  <span className="mt-1 text-[0.625rem] tabular-nums text-muted-foreground">
                    {core.cpu}
                  </span>
                  <span className="text-[0.625rem] tabular-nums">
                    {Math.round(core.usage)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
