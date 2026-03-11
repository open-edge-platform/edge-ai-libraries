import { useGetPipelinesQuery } from "@/api/api.generated";
import { PipelineCards } from "@/features/pipelines/PipelineCards";
import { PipelineCardsLoader } from "@/features/pipelines/PipelineCardsLoader";
import { useAppSelector } from "@/store/hooks";
import { compareDesc } from "date-fns";
import { selectPipelines } from "@/store/reducers/pipelines.ts";

export const Pipelines2 = () => {
  const { isLoading } = useGetPipelinesQuery();
  const pipelines = useAppSelector(selectPipelines);

  const sortedPipelines = pipelines
    ? [...pipelines].sort((p1, p2) =>
        compareDesc(new Date(p1.modified_at), new Date(p2.modified_at)),
      )
    : [];

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-4">
        {isLoading ? (
          <PipelineCardsLoader count={10} />
        ) : (
          <PipelineCards pipelines={sortedPipelines} source="pipelines" />
        )}
      </div>
    </div>
  );
};
