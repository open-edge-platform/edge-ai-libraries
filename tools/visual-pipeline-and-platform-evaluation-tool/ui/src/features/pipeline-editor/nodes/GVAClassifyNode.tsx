import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";
import type { DeviceType } from "@/features/pipeline-editor/nodes/shared-types.ts";
import { usePipelineEditorContext } from "../PipelineEditorContext.ts";

export const GVAClassifyNodeWidth = 300;

type GVAClassifyNodeProps = {
  data: {
    model?: string;
    device?: DeviceType;
  };
};

const GVAClassifyNode = ({ data }: GVAClassifyNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();

  return (
    <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-node-role-ai-classify-border min-w-[18.75rem]">
      <div className="flex gap-3">
        <div className="flex-shrink-0 w-10 h-10 rounded bg-node-role-ai-classify-surface flex items-center justify-center self-center">
          <svg
            className="w-6 h-6 text-node-role-ai-classify-icon"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"
            />
          </svg>
        </div>

        <div className="flex-1 flex flex-col">
          <div className="text-xl font-bold text-node-role-ai-classify-title">
            {simpleGraph ? "Image Classification" : "GVAClassify"}
          </div>

          <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
            {data.device && <span>{data.device}</span>}

            {data.model && (
              <>
                {data.device && <span className="text-node-separator">•</span>}
                <span
                  className="truncate max-w-[11.5625rem]"
                  title={data.model.split("/").pop() ?? data.model}
                >
                  {data.model.split("/").pop() ?? data.model}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 bg-node-role-ai-classify-handle!"
        style={{ left: getHandleLeftPosition("gvaclassify") }}
      />

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-node-role-ai-classify-handle!"
        style={{ left: getHandleLeftPosition("gvaclassify") }}
      />
    </div>
  );
};

export default GVAClassifyNode;
