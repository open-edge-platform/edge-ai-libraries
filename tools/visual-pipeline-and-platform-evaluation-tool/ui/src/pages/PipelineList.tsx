import { useSearchParams } from "react-router";
import {
  useGetPipelinesQuery,
  useListAudioPipelinesVoicePipelinesGetQuery,
} from "@/api/api.generated";
import { PipelineCards } from "@/features/pipelines/PipelineCards";
import { PipelineCardsLoader } from "@/features/pipelines/PipelineCardsLoader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAppSelector } from "@/store/hooks";
import { compareDesc } from "date-fns";
import { selectPipelines } from "@/store/reducers/pipelines.ts";

export const PipelineList = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "audio" ? "audio" : "vision";
  const { isLoading } = useGetPipelinesQuery();
  const {
    data: audioPipelines = [],
    isError: hasAudioError,
    isLoading: isLoadingAudio,
  } = useListAudioPipelinesVoicePipelinesGetQuery();
  const pipelines = useAppSelector(selectPipelines);

  const visionPipelines = (pipelines ? [...pipelines] : [])
    .filter((pipeline) => pipeline.type === "vision")
    .sort((p1, p2) =>
      compareDesc(new Date(p1.modified_at), new Date(p2.modified_at)),
    );

  return (
    <div className="flex-1 overflow-auto">
      <Tabs
        value={tab}
        onValueChange={(value) =>
          setSearchParams(value === "audio" ? { tab: value } : {}, {
            replace: true,
          })
        }
        className="p-4"
      >
        <TabsList>
          <TabsTrigger value="vision">Vision</TabsTrigger>
          <TabsTrigger value="audio">Audio</TabsTrigger>
        </TabsList>

        <TabsContent value="vision">
          {isLoading ? (
            <PipelineCardsLoader count={10} />
          ) : (
            <PipelineCards pipelines={visionPipelines} source="pipelines" />
          )}
        </TabsContent>

        <TabsContent value="audio">
          {isLoadingAudio ? (
            <PipelineCardsLoader count={2} />
          ) : hasAudioError ? (
            <p role="alert" className="text-sm text-destructive">
              Unable to load Audio pipelines.
            </p>
          ) : (
            <PipelineCards
              pipelines={audioPipelines}
              source="pipelines"
              createDisabled
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};
