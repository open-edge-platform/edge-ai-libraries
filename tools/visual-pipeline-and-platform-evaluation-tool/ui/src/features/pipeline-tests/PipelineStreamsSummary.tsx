import type { Pipeline, PipelineStreamSpec } from "@/api/api.generated.ts";
import { resolvePipelineVariantLabelFromReference } from "@/features/pipeline-tests/pipelineVariantReference";

interface PipelineStreamsSummaryProps {
  streamsPerPipeline: PipelineStreamSpec[];
  pipelines: Pipeline[];
  streamLabelResolver?: (
    item: PipelineStreamSpec,
    index: number,
  ) => {
    pipelineName: string;
    variantName: string | null;
  } | null;
}

export const PipelineStreamsSummary = ({
  streamsPerPipeline,
  pipelines,
  streamLabelResolver,
}: PipelineStreamsSummaryProps) => {
  if (streamsPerPipeline.length === 0) {
    return <p className="text-sm text-muted-foreground">No pipeline data</p>;
  }

  return (
    <div className="flex flex-wrap items-start gap-2">
      {streamsPerPipeline.map((item, index) => {
        const streams = item.streams ?? 0;
        const resolvedLabel = streamLabelResolver?.(item, index);
        const { pipelineName, variantName } =
          resolvedLabel ??
          resolvePipelineVariantLabelFromReference(pipelines, item.id);

        return (
          <div
            key={item.id}
            className="inline-flex w-fit max-w-full flex-col rounded-lg border border-blue-300/60 bg-neutral-950/50 px-3 py-2 relative overflow-hidden"
          >
            <div className="absolute inset-0 animate-[pulse_4s_ease-in-out_infinite] bg-gradient-to-r from-blue-500/10 via-blue-400/5 to-cyan-400/10" />
            <div className="relative min-w-0">
              <div className="min-w-0 flex items-center gap-2">
                <span className="truncate text-[10px] font-semibold uppercase tracking-wider text-blue-200">
                  {pipelineName}
                </span>
                {variantName && (
                  <>
                    <span className="text-[10px] text-blue-300/90">•</span>
                    <span className="truncate text-[10px] font-medium uppercase tracking-wider text-blue-300/90">
                      {variantName}
                    </span>
                  </>
                )}
              </div>
              <p className="mt-1 w-full text-center text-2xl font-bold leading-none text-white">
                {streams}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
};
