import type { Pipeline, PipelineDensitySpec } from "@/api/api.generated";

export type DensityMode = "classic" | "mixed" | "staged";

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

export interface StagedPipelineSelection extends MixedPipelineSelection {
  streamCpuCores: number[];
}

export const DEFAULT_MIXED_STREAMS = 1;

const STAGED_DEFAULT_PIPELINE = "Media Decode";

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

export const buildMixedDensitySpecs = (
  selections: MixedPipelineSelection[],
  streams: number,
): PipelineDensitySpec[] =>
  selections.map((selection, index) => ({
    pipeline: toVariantReference(selection),
    ...(index === 0 ? { streams } : {}),
  }));

/**
 * Defaults to the Media Decode pipeline: its GPU (VDBox) variant searched
 * first, then its CPU variant next to the VDBox maximum.
 */
export const createStagedSelections = (
  pipelines: Pipeline[],
): StagedPipelineSelection[] => {
  const decode = pipelines.find((p) => p.name === STAGED_DEFAULT_PIPELINE);
  if (decode) {
    const variantId = (name: string, fallback: number) =>
      (
        decode.variants.find((v) => v.name === name) ??
        decode.variants[fallback]
      )?.id ?? "";
    return [
      {
        pipelineId: decode.id,
        variantId: variantId("GPU", 0),
        streamCpuCores: [],
      },
      {
        pipelineId: decode.id,
        variantId: variantId("CPU", 0),
        streamCpuCores: [],
      },
    ];
  }
  return createMixedSelections(pipelines).map((selection) => ({
    ...selection,
    streamCpuCores: [],
  }));
};

export const isStagedSelectionValid = (
  selections: StagedPipelineSelection[],
): boolean =>
  selections.length >= 2 &&
  selections.every(
    (selection) => selection.pipelineId && selection.variantId,
  ) &&
  new Set(selections.map((s) => `${s.pipelineId}/${s.variantId}`)).size ===
    selections.length;

export const buildStagedDensitySpecs = (
  selections: StagedPipelineSelection[],
): PipelineDensitySpec[] =>
  selections.map((selection) => ({
    pipeline: toVariantReference(selection),
    stream_cpu_cores: selection.streamCpuCores,
  }));
