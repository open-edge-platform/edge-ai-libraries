import { usePipelineEditorContext } from "../PipelineEditorContext.ts";
import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const FileSrcNodeWidth = 260;

type FileSrcNodeProps = {
  data: {
    location: string;
  };
};

const FileSrcNode = ({ data }: FileSrcNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();

  return (
    <PipelineNodeCard
      title={simpleGraph ? "Input" : "FileSrc"}
      nodeType="filesrc"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.source}
      minWidthClass="min-w-[16.25rem]"
      handles="source"
      details={
        <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
          <span className="truncate max-w-[10.625rem]" title={data.location}>
            {data.location.split("/").pop() || data.location}
          </span>
        </div>
      }
      icon={
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      }
    />
  );
};

export default FileSrcNode;
