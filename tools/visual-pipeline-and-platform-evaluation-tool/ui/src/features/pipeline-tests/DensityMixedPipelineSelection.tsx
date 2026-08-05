import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import type { Pipeline } from "@/api/api.generated";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DEFAULT_MIXED_STREAMS,
  type MixedPipelineSelection,
} from "@/features/pipeline-tests/densitySelection";

interface DensityMixedPipelineSelectionProps {
  pipelines: Pipeline[];
  selections: MixedPipelineSelection[];
  onSelectionsChange: Dispatch<SetStateAction<MixedPipelineSelection[]>>;
  streams: number;
  onStreamsChange: (streams: number) => void;
  disabled?: boolean;
}

export const DensityMixedPipelineSelection = ({
  pipelines,
  selections,
  onSelectionsChange,
  streams,
  onStreamsChange,
  disabled = false,
}: DensityMixedPipelineSelectionProps) => {
  const [streamsInput, setStreamsInput] = useState(String(streams));

  useEffect(() => {
    setStreamsInput(String(streams));
  }, [streams]);

  const handlePipelineChange = (index: number, newPipelineId: string) => {
    onSelectionsChange((prev) =>
      prev.map((sel, idx) => {
        if (idx !== index) return sel;
        const newPipeline = pipelines.find((p) => p.id === newPipelineId);
        return {
          pipelineId: newPipelineId,
          variantId: newPipeline?.variants[0]?.id ?? "",
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

  const handleStreamsInputChange = (value: string) => {
    if (value !== "" && !/^\d+$/.test(value)) return;

    setStreamsInput(value);

    if (value === "") return;

    onStreamsChange(Number.parseInt(value, 10));
  };

  const handleStreamsBlur = () => {
    const parsedValue =
      streamsInput.trim().length === 0
        ? Number.NaN
        : Number.parseInt(streamsInput, 10);
    const normalizedValue =
      Number.isFinite(parsedValue) && parsedValue >= 1
        ? parsedValue
        : DEFAULT_MIXED_STREAMS;

    setStreamsInput(String(normalizedValue));
    onStreamsChange(normalizedValue);
  };

  return (
    <div className="space-y-3 pr-16">
      {selections.map((selection, index) => {
        const selectedPipeline = pipelines.find(
          (p) => p.id === selection.pipelineId,
        );
        const isFixed = index === 0;
        return (
          <div
            key={`mixed-${index}`}
            className="flex items-end gap-4 p-2 border bg-card"
          >
            <div className="flex-1">
              <label className="block text-sm font-medium mb-1">Pipeline</label>
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
              <label className="block text-sm font-medium mb-1">Variant</label>
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
              <label className="block text-sm font-medium mb-1">Streams</label>
              {isFixed ? (
                <Input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  value={streamsInput}
                  disabled={disabled}
                  onChange={(event) =>
                    handleStreamsInputChange(event.target.value)
                  }
                  onBlur={handleStreamsBlur}
                  className="w-24"
                />
              ) : (
                <p className="text-sm text-muted-foreground h-9 flex items-center">
                  Incremented by the benchmark
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
