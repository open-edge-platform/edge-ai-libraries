import type { Pipeline } from "@/api/api.generated";

export interface PipelineVariantReference {
  rawKey: string;
  pipelineId: string;
  variantId: string | undefined;
}

export interface PipelineVariantLabel {
  pipelineName: string;
  variantName: string | undefined;
}

export const parsePipelineVariantReference = (
  value: string,
): PipelineVariantReference => {
  const variantPathMatch = value.match(
    /^\/?pipelines\/([^/]+)\/variants\/([^/]+)$/,
  );
  if (!variantPathMatch) {
    return {
      rawKey: value,
      pipelineId: value,
      variantId: undefined,
    };
  }

  const [, rawPipelineId, rawVariantId] = variantPathMatch;

  return {
    rawKey: value,
    pipelineId: decodeURIComponent(rawPipelineId),
    variantId: decodeURIComponent(rawVariantId),
  };
};

export const resolvePipelineVariantLabel = (
  pipelines: Pipeline[],
  pipelineId: string,
  variantId: string | undefined,
): PipelineVariantLabel => {
  const pipeline = pipelines.find((item) => item.id === pipelineId);
  const variant = variantId
    ? pipeline?.variants.find((item) => item.id === variantId)
    : null;

  return {
    pipelineName: pipeline?.name ?? pipelineId,
    variantName: variant?.name ?? variantId,
  };
};

export const resolvePipelineVariantLabelFromReference = (
  pipelines: Pipeline[],
  reference: string,
): PipelineVariantLabel => {
  const { pipelineId, variantId } = parsePipelineVariantReference(reference);
  return resolvePipelineVariantLabel(pipelines, pipelineId, variantId);
};
