import type { Pipeline, PipelineStreamSpec } from "@/api/api.generated.ts";

interface PipelineStreamsSummaryProps {
  streamsPerPipeline: PipelineStreamSpec[];
  pipelines: Pipeline[];
}

export const PipelineStreamsSummary = ({
  streamsPerPipeline,
  pipelines,
}: PipelineStreamsSummaryProps) => {
  const maxStreams = Math.max(
    ...streamsPerPipeline.map((pipeline) => pipeline.streams ?? 0),
    1,
  );

  const getPipelineName = (pipelineId: string) => {
    const pipeline = pipelines.find((p) => p.id === pipelineId);
    return pipeline?.name ?? pipelineId;
  };

  return (
    <div className="space-y-3">
      {streamsPerPipeline.map((item) => {
        const streams = item.streams ?? 0;
        const percentage = (streams / maxStreams) * 100;

        return (
          <div key={item.id} className="space-y-1.5">
            <div className="flex justify-between items-center text-sm">
              <span className="font-medium text-neutral-300">
                {getPipelineName(item.id)}
              </span>
              <span className="text-white font-bold">{streams} streams</span>
            </div>
            <div className="h-2 bg-neutral-800/50 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 transition-all duration-500 rounded-full"
                style={{ width: `${percentage}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
};
