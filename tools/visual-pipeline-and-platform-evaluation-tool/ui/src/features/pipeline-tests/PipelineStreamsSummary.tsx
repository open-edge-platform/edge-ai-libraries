import type { Pipeline, PipelinePerformanceSpec } from "@/api/api.generated.ts";

interface PipelineStreamsSummaryProps {
  streamsPerPipeline: PipelinePerformanceSpec[];
  pipelines: Pipeline[];
}

export const PipelineStreamsSummary = ({
  streamsPerPipeline,
  pipelines,
}: PipelineStreamsSummaryProps) => {
  const getPipelineName = (pipelineId: string) => {
    const pipeline = pipelines.find((p) => p.id === pipelineId);
    return pipeline?.name ?? pipelineId;
  };

  return (
    <div className="space-y-1">
      {streamsPerPipeline.map((item) => (
        <div key={item.id} className="text-sm">
          <span className="font-medium">{getPipelineName(item.id)}:</span>{" "}
          <span className="text-green-700 dark:text-green-300">
            {item.streams ?? 0} streams
          </span>
        </div>
      ))}
    </div>
  );
};
