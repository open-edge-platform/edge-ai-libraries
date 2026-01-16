import { usePipelineName } from "@/hooks/usePipelines";

interface PipelineNameProps {
  pipelineId: string;
}

export const PipelineName = ({ pipelineId }: PipelineNameProps) => {
  const name = usePipelineName(pipelineId);

  return <>{name}</>;
};
