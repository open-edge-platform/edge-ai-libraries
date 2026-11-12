import type { Dispatch, SetStateAction } from "react";
import type { Pipeline } from "@/api/api.generated";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { StagedPipelineSelection } from "@/features/pipeline-tests/densitySelection";
import { StreamCpuCoresButton } from "@/features/pipeline-tests/StreamCpuCoresButton";

interface DensityStagedPipelineSelectionProps {
  pipelines: Pipeline[];
  selections: StagedPipelineSelection[];
  onSelectionsChange: Dispatch<SetStateAction<StagedPipelineSelection[]>>;
  disabled?: boolean;
}

const STAGE_LABELS = [
  "Stage 1 - searched alone (e.g. GPU / VDBox decode)",
  "Stage 2 - searched next to the stage 1 maximum (e.g. CPU decode)",
];

export const DensityStagedPipelineSelection = ({
  pipelines,
  selections,
  onSelectionsChange,
  disabled = false,
}: DensityStagedPipelineSelectionProps) => {
  const update = (
    index: number,
    change: (selection: StagedPipelineSelection) => StagedPipelineSelection,
  ) =>
    onSelectionsChange((prev) =>
      prev.map((selection, idx) =>
        idx === index ? change(selection) : selection,
      ),
    );

  return (
    <div className="space-y-3 pr-16">
      {selections.map((selection, index) => {
        const selectedPipeline = pipelines.find(
          (p) => p.id === selection.pipelineId,
        );
        return (
          <div key={`staged-${index}`} className="p-2 border bg-card">
            <p className="text-xs text-muted-foreground mb-2">
              {STAGE_LABELS[index] ?? `Stage ${index + 1}`}
            </p>
            <div className="flex items-end gap-4">
              <div className="flex-1">
                <label className="block text-sm font-medium mb-1">
                  Pipeline
                </label>
                <Select
                  value={selection.pipelineId}
                  onValueChange={(value) =>
                    update(index, (sel) => ({
                      ...sel,
                      pipelineId: value,
                      variantId:
                        pipelines.find((p) => p.id === value)?.variants[0]
                          ?.id ?? "",
                    }))
                  }
                  disabled={disabled}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {pipelines.map((pipeline) => (
                      <SelectItem key={pipeline.id} value={pipeline.id}>
                        {pipeline.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex-1">
                <label className="block text-sm font-medium mb-1">
                  Variant
                </label>
                <Select
                  value={selection.variantId}
                  onValueChange={(value) =>
                    update(index, (sel) => ({ ...sel, variantId: value }))
                  }
                  disabled={disabled}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {selectedPipeline?.variants.map((variant) => (
                      <SelectItem key={variant.id} value={variant.id}>
                        {variant.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex-1">
                <label className="block text-sm font-medium mb-1">
                  CPU cores per stream
                </label>
                <StreamCpuCoresButton
                  cores={selection.streamCpuCores}
                  onChange={(cores) =>
                    update(index, (sel) => ({ ...sel, streamCpuCores: cores }))
                  }
                  disabled={disabled}
                />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
