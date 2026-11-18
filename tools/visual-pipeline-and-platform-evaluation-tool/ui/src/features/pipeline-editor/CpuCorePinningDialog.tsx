import { useEffect, useMemo, useState } from "react";
import { TriangleAlert } from "lucide-react";

import type { CpuCore, CpuCoreType } from "@/api/api.generated";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useAppSelector } from "@/store/hooks";
import { selectCpuTopology } from "@/store/reducers/devices";

const CORE_TYPE_ORDER: CpuCoreType[] = ["P", "E", "LPE", "UNIFORM"];

const CORE_TYPE_LABELS: Record<CpuCoreType, string> = {
  P: "Performance cores (P)",
  E: "Efficient cores (E)",
  LPE: "Low-power efficient cores (LPE)",
  UNIFORM: "CPU cores",
};

const CORE_TYPE_DESCRIPTIONS: Record<CpuCoreType, string> = {
  P: "Highest throughput per stream.",
  E: "Higher aggregate throughput per watt.",
  LPE: "Lowest power. Inference cannot run on LPE cores alone.",
  UNIFORM: "This CPU has a single core type.",
};

type CpuCorePinningDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Empty means all cores. */
  pinnedCores: number[];
  onApply: (cores: number[]) => void;
};

const formatCoreList = (cores: number[]): string => {
  if (cores.length === 0) {
    return "";
  }

  const sorted = [...cores].sort((a, b) => a - b);
  const ranges: string[] = [];
  let start = sorted[0];
  let previous = sorted[0];

  for (const cpu of sorted.slice(1)) {
    if (cpu === previous + 1) {
      previous = cpu;
      continue;
    }
    ranges.push(start === previous ? `${start}` : `${start}-${previous}`);
    start = cpu;
    previous = cpu;
  }
  ranges.push(start === previous ? `${start}` : `${start}-${previous}`);

  return ranges.join(",");
};

export const CpuCorePinningDialog = ({
  open,
  onOpenChange,
  pinnedCores,
  onApply,
}: CpuCorePinningDialogProps) => {
  const topology = useAppSelector(selectCpuTopology);
  const [draft, setDraft] = useState<number[]>(pinnedCores);

  useEffect(() => {
    if (open) {
      setDraft(pinnedCores);
    }
  }, [open, pinnedCores]);

  const groups = useMemo(() => {
    const cores = topology?.cores ?? [];
    const byType = new Map<CpuCoreType, CpuCore[]>();

    for (const core of cores) {
      const existing = byType.get(core.core_type);
      if (existing) {
        existing.push(core);
      } else {
        byType.set(core.core_type, [core]);
      }
    }

    return CORE_TYPE_ORDER.filter((type) => byType.has(type)).map((type) => ({
      type,
      cores: [...byType.get(type)!].sort((a, b) => a.cpu - b.cpu),
    }));
  }, [topology]);

  const draftSet = useMemo(() => new Set(draft), [draft]);

  const lpeCpus = useMemo(
    () =>
      new Set(
        (topology?.cores ?? [])
          .filter((core) => core.core_type === "LPE")
          .map((core) => core.cpu),
      ),
    [topology],
  );

  const isLpeOnlySelection =
    draft.length > 0 && draft.every((cpu) => lpeCpus.has(cpu));

  const toggleCpu = (cpu: number, checked: boolean) => {
    setDraft((previous) =>
      checked
        ? [...previous, cpu].sort((a, b) => a - b)
        : previous.filter((value) => value !== cpu),
    );
  };

  const toggleGroup = (cores: CpuCore[], checked: boolean) => {
    const groupCpus = cores.map((core) => core.cpu);

    setDraft((previous) => {
      const remaining = previous.filter((cpu) => !groupCpus.includes(cpu));
      return checked
        ? [...remaining, ...groupCpus].sort((a, b) => a - b)
        : remaining;
    });
  };

  const handleApply = () => {
    onApply([...draft].sort((a, b) => a - b));
    onOpenChange(false);
  };

  const hasTopology = groups.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>CPU core pinning</DialogTitle>
          <DialogDescription>
            Select the logical CPU cores this pipeline variant may run on. With
            no cores selected the pipeline runs on all cores.
          </DialogDescription>
        </DialogHeader>

        {hasTopology ? (
          <>
            <div className="max-h-[50vh] space-y-4 overflow-y-auto pr-1">
              {groups.map((group, index) => {
                const groupCpus = group.cores.map((core) => core.cpu);
                const selectedInGroup = groupCpus.filter((cpu) =>
                  draftSet.has(cpu),
                ).length;
                const allSelected = selectedInGroup === groupCpus.length;

                return (
                  <div key={group.type} className="space-y-2">
                    {index > 0 && <Separator className="mb-4" />}

                    <label className="flex cursor-pointer items-center gap-2">
                      <Checkbox
                        checked={allSelected}
                        aria-label={`Select all ${CORE_TYPE_LABELS[group.type]}`}
                        onCheckedChange={(checked) =>
                          toggleGroup(group.cores, checked === true)
                        }
                      />
                      <span className="text-sm font-medium">
                        {CORE_TYPE_LABELS[group.type]}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {selectedInGroup} / {groupCpus.length} selected
                      </span>
                    </label>

                    <p className="pl-6 text-xs text-muted-foreground">
                      {CORE_TYPE_DESCRIPTIONS[group.type]}
                    </p>

                    <div className="flex flex-wrap gap-x-2.5 gap-y-2 pl-6">
                      {group.cores.map((core) => (
                        <label
                          key={core.cpu}
                          className="flex cursor-pointer items-center gap-1.5"
                          title={`Logical CPU ${core.cpu} on physical core ${core.core_id}`}
                        >
                          <Checkbox
                            checked={draftSet.has(core.cpu)}
                            aria-label={`CPU ${core.cpu}`}
                            onCheckedChange={(checked) =>
                              toggleCpu(core.cpu, checked === true)
                            }
                          />
                          <span className="text-sm tabular-nums">
                            {core.cpu}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>

            {isLpeOnlySelection && (
              <div className="flex items-start gap-2 border border-destructive/40 bg-destructive/10 p-2 text-xs">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                <span>
                  Only low-power efficient cores are selected. OpenVINO refuses
                  to run inference when no P or E core is available. Add at
                  least one P or E core to continue.
                </span>
              </div>
            )}

            <p className="text-xs text-muted-foreground">
              {draft.length === 0
                ? "No cores selected - all cores will be used."
                : `Selected ${draft.length} of ${topology?.cores.length ?? 0} cores: ${formatCoreList(draft)}`}
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            CPU core types are not available on this system, so cores cannot be
            selected.
          </p>
        )}

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => setDraft([])}
            disabled={!hasTopology || draft.length === 0}
          >
            Clear
          </Button>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleApply}
            disabled={!hasTopology || isLpeOnlySelection}
          >
            Apply
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default CpuCorePinningDialog;
