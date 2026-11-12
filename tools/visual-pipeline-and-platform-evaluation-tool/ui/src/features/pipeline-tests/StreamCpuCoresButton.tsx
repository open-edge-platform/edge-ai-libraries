import { useState } from "react";
import { Pin } from "lucide-react";

import { Button } from "@/components/ui/button";
import { CpuCorePinningDialog } from "@/features/pipeline-editor/CpuCorePinningDialog";
import { formatCoreList } from "@/features/pipeline-editor/cpuCores";

type StreamCpuCoresButtonProps = {
  cores: number[];
  onChange: (cores: number[]) => void;
  disabled?: boolean;
};

export const StreamCpuCoresButton = ({
  cores,
  onChange,
  disabled = false,
}: StreamCpuCoresButtonProps) => {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        type="button"
        variant="outline"
        onClick={() => setOpen(true)}
        disabled={disabled}
        aria-label="CPU cores for the streams of this pipeline"
        className="w-full justify-start"
      >
        <Pin className={cores.length > 0 ? "text-brand-accent" : undefined} />
        <span className="truncate tabular-nums">
          {cores.length > 0 ? formatCoreList(cores) : "All cores"}
        </span>
      </Button>
      <CpuCorePinningDialog
        open={open}
        onOpenChange={setOpen}
        pinnedCores={cores}
        onApply={onChange}
        description="Each stream of this pipeline is pinned to one of the selected cores, in round-robin order, like running every stream under taskset -c <core>. With no cores selected the streams run on all cores."
        allowLpeOnly
      />
    </>
  );
};
