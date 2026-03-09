import { usePipelineName, useVariantName } from "@/hooks/usePipelines.ts";

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
