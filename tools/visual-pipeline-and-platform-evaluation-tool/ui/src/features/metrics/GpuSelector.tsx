import { cn } from "@/lib/utils";

interface GpuSelectorProps {
  availableGpus: number[];
  onGpuChange: (gpuId: number) => void;
  selectedGpu: number;
}

export const GpuSelector = ({
  availableGpus,
  onGpuChange,
  selectedGpu,
}: GpuSelectorProps) => {
  if (availableGpus.length <= 1) {
    return null;
  }

  return (
    <div className="flex flex-col justify-evenly h-[15rem]">
      {availableGpus.map((gpuId) => (
        <button
          key={gpuId}
          onClick={() => onGpuChange(gpuId)}
          className={cn(
            "py-1 text-sm font-medium transition-all text-left whitespace-nowrap",
            selectedGpu === gpuId
              ? "text-foreground"
              : "text-muted-foreground hover:text-foreground/70",
          )}
        >
          GPU {gpuId}
        </button>
      ))}
    </div>
  );
};
