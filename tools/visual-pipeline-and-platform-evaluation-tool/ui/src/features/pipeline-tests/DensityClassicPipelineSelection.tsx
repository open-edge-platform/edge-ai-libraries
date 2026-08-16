import type { Dispatch, SetStateAction } from "react";
import { Plus, X } from "lucide-react";
import type { Pipeline } from "@/api/api.generated";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ParticipationSlider } from "@/features/pipeline-tests/ParticipationSlider";
import {
  distributeStreamRates,
  type ClassicPipelineSelection,
} from "@/features/pipeline-tests/densitySelection";
import { useStreamRateChange } from "@/hooks/useStreamRateChange";
import { cn } from "@/lib/utils";

interface DensityClassicPipelineSelectionProps {
  pipelines: Pipeline[];
  selections: ClassicPipelineSelection[];
  onSelectionsChange: Dispatch<SetStateAction<ClassicPipelineSelection[]>>;
  disabled?: boolean;
}

const ANIMATION_DURATION_MS = 300;

export const DensityClassicPipelineSelection = ({
  pipelines,
  selections,
  onSelectionsChange,
  disabled = false,
}: DensityClassicPipelineSelectionProps) => {
  const handleStreamRateChange = useStreamRateChange(onSelectionsChange);

  const handleAddPipeline = () => {
    const usedPipelineIds = selections.map((sel) => sel.pipelineId);
    const availablePipeline = pipelines.find(
      (pipeline) => !usedPipelineIds.includes(pipeline.id),
    );
    const firstVariant = availablePipeline?.variants[0];
    if (!availablePipeline || !firstVariant) return;

    onSelectionsChange((prev) =>
      distributeStreamRates([
        ...prev,
        {
          pipelineId: availablePipeline.id,
          variantId: firstVariant.id,
          stream_rate: 0,
          isNew: true,
        },
      ]),
    );

    setTimeout(() => {
      onSelectionsChange((prev) =>
        prev.map((sel, idx) =>
          idx === prev.length - 1 ? { ...sel, isNew: false } : sel,
        ),
      );
    }, ANIMATION_DURATION_MS);
  };

  const handleRemovePipeline = (pipelineId: string) => {
    if (selections.length <= 1) return;

    onSelectionsChange((prev) =>
      prev.map((sel) =>
        sel.pipelineId === pipelineId ? { ...sel, isRemoving: true } : sel,
      ),
    );

    setTimeout(() => {
      onSelectionsChange((prev) =>
        distributeStreamRates(
          prev.filter((sel) => sel.pipelineId !== pipelineId),
        ),
      );
    }, ANIMATION_DURATION_MS);
  };

  const handlePipelineChange = (index: number, newPipelineId: string) => {
    onSelectionsChange((prev) =>
      prev.map((sel, idx) => {
        if (idx !== index) return sel;
        const newPipeline = pipelines.find((p) => p.id === newPipelineId);
        return {
          ...sel,
          pipelineId: newPipelineId,
          variantId: newPipeline?.variants[0]?.id ?? sel.variantId,
        };
      }),
    );
  };

  const handleVariantChange = (index: number, newVariantId: string) => {
    onSelectionsChange((prev) =>
      prev.map((sel, idx) =>
        idx === index ? { ...sel, variantId: newVariantId } : sel,
      ),
    );
  };

  return (
    <div className="space-y-3 pr-16">
      {selections.map((selection, index) => {
        const selectedPipeline = pipelines.find(
          (p) => p.id === selection.pipelineId,
        );
        return (
          <div
            key={`${selection.pipelineId}-${index}`}
            className={cn(
              "flex items-center gap-3 p-2 border bg-card transition-all duration-300",
              selection.isRemoving
                ? "opacity-0 -translate-y-2"
                : selection.isNew
                  ? "animate-in fade-in slide-in-from-top-2"
                  : "",
            )}
          >
            <div className="flex-1 flex items-center gap-4">
              <div className="flex-1">
                <label className="block text-sm font-medium mb-1">
                  Pipeline
                </label>
                <Select
                  value={selection.pipelineId}
                  onValueChange={(value) => handlePipelineChange(index, value)}
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
                  onValueChange={(value) => handleVariantChange(index, value)}
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
                  Participation Rate
                </label>
                <ParticipationSlider
                  value={selection.stream_rate}
                  onChange={(val) => handleStreamRateChange(index, val)}
                  min={0}
                  max={100}
                  disabled={disabled}
                />
              </div>
            </div>

            {selections.length > 1 && (
              <Button
                onClick={() => handleRemovePipeline(selection.pipelineId)}
                variant="ghost"
                size="icon"
                className="text-destructive"
                disabled={disabled}
              >
                <X className="w-5 h-5" />
              </Button>
            )}
          </div>
        );
      })}

      <Button
        onClick={handleAddPipeline}
        variant="outline"
        disabled={selections.length >= pipelines.length || disabled}
      >
        <Plus className="w-5 h-5" />
        <span>Add Pipeline</span>
      </Button>
    </div>
  );
};
