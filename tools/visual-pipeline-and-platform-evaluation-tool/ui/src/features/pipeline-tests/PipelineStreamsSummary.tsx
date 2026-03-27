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
            className="inline-flex w-fit max-w-full flex-col rounded-lg border border-pipeline-summary-border bg-surface-overlay px-3 py-2 relative overflow-hidden"
          >
            <div className="absolute inset-0 animate-[pulse_4s_ease-in-out_infinite] bg-gradient-to-r from-pipeline-summary-glow-from via-pipeline-summary-glow-via to-pipeline-summary-glow-to" />
            <div className="relative min-w-0">
              <div className="min-w-0 flex items-center gap-2">
                <span className="truncate text-[0.625rem] font-semibold uppercase tracking-wider text-pipeline-summary-title">
                  {pipelineName}
                </span>
                {variantName && (
                  <>
                    <span className="text-[0.625rem] text-pipeline-summary-variant">•</span>
                    <span className="truncate text-[0.625rem] font-medium uppercase tracking-wider text-pipeline-summary-variant">
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
