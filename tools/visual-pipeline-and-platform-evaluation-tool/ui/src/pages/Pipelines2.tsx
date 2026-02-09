import { useGetPipelinesQuery } from "@/api/api.generated";
import { PipelineCards } from "@/features/pipelines/PipelineCards";
import { PipelineCardsLoader } from "@/features/pipelines/PipelineCardsLoader";
import { compareDesc } from "date-fns";

export const Pipelines2 = () => {
  const { data: pipelines, isLoading, error } = useGetPipelinesQuery();

  if (error) return <div>Error loading pipelines</div>;

  const sortedPipelines = pipelines
    ? [...pipelines].sort((p1, p2) =>
        compareDesc(new Date(p2.modified_at), new Date(p1.modified_at)),
      )
    : [];

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-4">
        {isLoading ? (
          <PipelineCardsLoader count={10} />
        ) : (
          <PipelineCards pipelines={sortedPipelines} />
        )}
      </div>
    </div>
  );
};
