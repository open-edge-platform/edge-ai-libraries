import {
  useGetPipelinesQuery,
  useListAudioPipelinesVoicePipelinesGetQuery,
} from "@/api/api.generated";
import { PipelineCards } from "@/features/pipelines/PipelineCards";
import { useAppSelector } from "@/store/hooks";
import { compareDesc } from "date-fns";
import { selectPipelines } from "@/store/reducers/pipelines.ts";
import { AudioPipelineCards } from "@/features/voice/AudioPipelineCards";

export const PipelineList = () => {
  const { isLoading } = useGetPipelinesQuery();
  const {
    data: audioPipelines = [],
    isError: hasAudioError,
    isLoading: isLoadingAudio,
  } = useListAudioPipelinesVoicePipelinesGetQuery();
  const pipelines = useAppSelector(selectPipelines);

  const sortedPipelines = pipelines
    ? [...pipelines].sort((p1, p2) =>
        compareDesc(new Date(p1.modified_at), new Date(p2.modified_at)),
      )
    : [];
  const visionPipelines = sortedPipelines.filter(
    (pipeline) => pipeline.type === "vision",
  );
  const timeSeriesPipelines = sortedPipelines.filter(
    (pipeline) => pipeline.type === "time_series",
  );
  const isLoadingCatalog = isLoading || isLoadingAudio;

  return (
    <div className="flex-1 overflow-auto">
      <div className="space-y-8 p-4">
        <PipelineCards pipelines={[]} source="pipelines" />
        {!isLoadingCatalog && visionPipelines.length > 0 && (
          <section
            aria-labelledby="vision-pipelines-heading"
            className="space-y-4"
          >
            <h2 id="vision-pipelines-heading" className="text-lg font-semibold">
              Vision
            </h2>
            <PipelineCards
              pipelines={visionPipelines}
              source="pipelines"
              showCreate={false}
            />
          </section>
        )}
        {!isLoadingCatalog && timeSeriesPipelines.length > 0 && (
          <section
            aria-labelledby="time-series-pipelines-heading"
            className="space-y-4"
          >
            <h2
              id="time-series-pipelines-heading"
              className="text-lg font-semibold"
            >
              Time Series
            </h2>
            <PipelineCards
              pipelines={timeSeriesPipelines}
              source="pipelines"
              showCreate={false}
            />
          </section>
        )}
        {!isLoadingCatalog && (hasAudioError || audioPipelines.length > 0) && (
          <section
            aria-labelledby="audio-pipelines-heading"
            className="space-y-4"
          >
            <h2 id="audio-pipelines-heading" className="text-lg font-semibold">
              Audio
            </h2>
            <AudioPipelineCards
              pipelines={audioPipelines}
              hasError={hasAudioError}
            />
          </section>
        )}
      </div>
    </div>
  );
};
