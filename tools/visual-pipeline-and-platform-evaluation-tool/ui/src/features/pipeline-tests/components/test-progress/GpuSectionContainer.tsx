import { GpuSelector } from "@/features/metrics/GpuSelector";
import { cn } from "@/lib/utils";

interface GpuSectionContainerProps {
  title: React.ReactNode;
  availableGpus: number[];
  selectedGpu: number;
  onGpuChange: (gpuId: number) => void;
  useDemoStyles: boolean;
  forceDark: boolean;
  isSummary: boolean;
  summarySectionClassName: string;
  summaryTitleClassName: string;
  children: React.ReactNode;
}

export const GpuSectionContainer = ({
  title,
  availableGpus,
  selectedGpu,
  onGpuChange,
  useDemoStyles,
  forceDark,
  isSummary,
  summarySectionClassName,
  summaryTitleClassName,
  children,
}: GpuSectionContainerProps) => (
  <div
    className={cn(
      `${
        useDemoStyles
          ? `${forceDark ? "bg-surface-overlay" : "bg-card/80"}`
          : "bg-background"
      } ${useDemoStyles ? "rounded-xl shadow-2xl p-6" : "shadow-md p-4"} ${
        isSummary
          ? summarySectionClassName
          : useDemoStyles
            ? forceDark
              ? "border border-surface-overlay-border"
              : "border border-border"
            : ""
      }`,
    )}
  >
    <h3
      className={cn(
        `${
          useDemoStyles
            ? `text-[0.625rem] font-semibold uppercase tracking-widest mb-6 ${
                isSummary ? summaryTitleClassName : "text-muted-foreground"
              }`
            : "text-sm font-medium text-foreground mb-5"
        }`,
      )}
    >
      {title}
    </h3>
    <div className="flex gap-4 items-stretch overflow-hidden">
      <div className="flex">
        <GpuSelector
          availableGpus={availableGpus}
          selectedGpu={selectedGpu}
          onGpuChange={onGpuChange}
        />
      </div>
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  </div>
);
