import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";
import { usePipelineEditorContext } from "../PipelineEditorContext.ts";

export const GVADetectNodeWidth = 280;

type GVADetectNodeProps = {
  data: {
    model?: string;
    device?: string;
    "object-class": string;
  };
};

const GVADetectNode = ({ data }: GVADetectNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();

  return (
    <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-node-role-ai-detect-border min-w-[17.5rem]">
      <div className="flex gap-3">
        <div className="shrink-0 w-10 h-10 rounded bg-node-role-ai-detect-surface flex items-center justify-center self-center">
          <svg
            className="w-6 h-6 text-node-role-ai-detect-icon"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
            />
          </svg>
        </div>

        <div className="flex-1 flex flex-col">
          <div className="text-xl font-bold text-node-role-ai-detect-title">
            {simpleGraph ? "Object Detection" : "GVADetect"}
          </div>

          <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
            {data.device && <span>{data.device}</span>}

            {data.model && (
              <>
                {data.device && <span className="text-node-separator">•</span>}
                <span
                  className="truncate max-w-[10.3125rem]"
                  title={data.model.split("/").pop() || data.model}
                >
                  {data.model.split("/").pop() || data.model}
                </span>
              </>
            )}

            {data["object-class"] && (
              <>
                {(data.model || data.device) && (
                  <span className="text-node-separator">•</span>
                )}
                <span>{data["object-class"]}</span>
              </>
            )}
          </div>
        </div>
      </div>

      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 bg-node-role-ai-detect-handle!"
        style={{ left: getHandleLeftPosition("gvadetect") }}
      />

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-node-role-ai-detect-handle!"
        style={{ left: getHandleLeftPosition("gvadetect") }}
      />
    </div>
  );
};

export default GVADetectNode;
