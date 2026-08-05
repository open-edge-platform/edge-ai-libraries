import type { Pipeline, PipelineDensitySpec } from "@/api/api.generated";

export type DensityMode = "classic" | "mixed";

export interface ClassicPipelineSelection {
  pipelineId: string;
  variantId: string;
  stream_rate: number;
  isRemoving?: boolean;
  isNew?: boolean;
}

export interface MixedPipelineSelection {
  pipelineId: string;
  variantId: string;
}

export const DEFAULT_MIXED_STREAMS = 1;

/** Spreads 100% evenly across the selections, giving the remainder to the first one. */
export const distributeStreamRates = <T extends { stream_rate: number }>(
  selections: T[],
): T[] => {
  const count = selections.length;
  if (count === 0) return selections;

  const baseRate = Math.floor(100 / count);
  const remainder = 100 - baseRate * count;

  return selections.map((selection, index) => ({
    ...selection,
    stream_rate: index === 0 ? baseRate + remainder : baseRate,
  }));
};

export const createClassicSelections = (
  pipelines: Pipeline[],
): ClassicPipelineSelection[] => {
  const firstPipeline = pipelines[0];
  if (!firstPipeline) return [];

  return [
    {
      pipelineId: firstPipeline.id,
      variantId: firstPipeline.variants[0]?.id ?? "",
      stream_rate: 100,
      isNew: false,
    },
  ];
};

export const createMixedSelections = (
  pipelines: Pipeline[],
): MixedPipelineSelection[] => {
  const firstPipeline = pipelines[0];
  if (!firstPipeline) return [];

  const secondPipeline = pipelines[1] ?? firstPipeline;

  return [
    {
      pipelineId: firstPipeline.id,
      variantId: firstPipeline.variants[0]?.id ?? "",
    },
    {
      pipelineId: secondPipeline.id,
      variantId: secondPipeline.variants[0]?.id ?? "",
    },
  ];
};

const toVariantReference = (selection: MixedPipelineSelection) =>
  ({
    source: "variant",
    pipeline_id: selection.pipelineId,
    variant_id: selection.variantId,
  }) as const;

export const isClassicSelectionValid = (
  selections: ClassicPipelineSelection[],
): boolean =>
  selections.length > 0 &&
  selections.every((selection) => selection.pipelineId && selection.variantId);

export const isMixedSelectionValid = (
  selections: MixedPipelineSelection[],
  streams: number,
): boolean =>
  selections.length === 2 &&
  selections.every(
    (selection) => selection.pipelineId && selection.variantId,
  ) &&
  Number.isFinite(streams) &&
  streams >= 1;

export const buildClassicDensitySpecs = (
  selections: ClassicPipelineSelection[],
): PipelineDensitySpec[] =>
  selections.map((selection) => ({
    pipeline: toVariantReference(selection),
    stream_rate: selection.stream_rate,
  }));

/**
 * Only the first spec carries `streams`, which switches the backend into
 * mixed-density mode: the first pipeline is pinned to that number of streams
 * while the second one is incremented by the benchmark algorithm.
 */
export const buildMixedDensitySpecs = (
  selections: MixedPipelineSelection[],
  streams: number,
): PipelineDensitySpec[] =>
  selections.map((selection, index) => ({
    pipeline: toVariantReference(selection),
    ...(index === 0 ? { streams } : {}),
  }));
