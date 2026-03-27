import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";
import { usePipelineEditorContext } from "../PipelineEditorContext.ts";

export const FileSrcNodeWidth = 260;

type FileSrcNodeProps = {
  data: {
    location: string;
  };
};

const FileSrcNode = ({ data }: FileSrcNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();

  return (
    <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-node-role-source-border min-w-[16.25rem]">
      <div className="flex gap-3">
        <div className="shrink-0 w-10 h-10 rounded bg-node-role-source-surface flex items-center justify-center self-center">
          <svg
            className="w-6 h-6 text-node-role-source-icon"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        </div>

        <div className="flex-1 flex flex-col">
          <div className="text-xl font-bold text-node-role-source-title">
            {simpleGraph ? "Input" : "FileSrc"}
          </div>

          <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
            <span className="truncate max-w-[10.625rem]" title={data.location}>
              {data.location.split("/").pop() || data.location}
            </span>
          </div>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-node-role-source-handle!"
        style={{ left: getHandleLeftPosition("filesrc") }}
      />
    </div>
  );
};

export default FileSrcNode;
