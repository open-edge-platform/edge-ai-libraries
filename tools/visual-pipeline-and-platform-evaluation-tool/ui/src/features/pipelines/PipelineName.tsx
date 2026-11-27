import { usePipelineName, useVariantName } from "@/hooks/usePipelines.ts";
import { parsePipelineVariantReference } from "@/features/pipeline-tests/pipelineVariantReference";

interface PipelineNameProps {
  pipelineId: string;
  variantId?: string;
}

export const PipelineName = ({ pipelineId, variantId }: PipelineNameProps) => {
  const pipelineName = usePipelineName(pipelineId);
  const variantName = useVariantName(pipelineId, variantId);

  if (variantName) {
    return (
      <>
        {pipelineName} • {variantName}
      </>
    );
  }

  return <>{pipelineName}</>;
};

interface PipelineReferenceNameProps {
  reference: string;
}

/** Renders a pipeline name from a plain pipeline id or a `/pipelines/{id}/variants/{id}` reference. */
export const PipelineReferenceName = ({
  reference,
}: PipelineReferenceNameProps) => {
  const { pipelineId, variantId } = parsePipelineVariantReference(reference);
  return <PipelineName pipelineId={pipelineId} variantId={variantId} />;
};
