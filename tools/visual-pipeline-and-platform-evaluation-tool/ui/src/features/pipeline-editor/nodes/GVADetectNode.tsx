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
    <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-indigo-400 min-w-[280px]">
      <div className="flex gap-3">
        <div className="shrink-0 w-10 h-10 rounded bg-indigo-100 dark:bg-indigo-900 flex items-center justify-center self-center">
          <svg
            className="w-6 h-6 text-indigo-600 dark:text-indigo-400"
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
          <div className="text-xl font-bold text-indigo-700 dark:text-indigo-300">
            {simpleGraph ? "Object Detection" : "GVADetect"}
          </div>

          <div className="flex items-center gap-1 flex-wrap text-xs text-gray-700 dark:text-gray-300">
            {data.device && <span>{data.device}</span>}

            {data.model && (
              <>
                {data.device && <span className="text-gray-400">•</span>}
                <span
                  className="truncate max-w-[165px]"
                  title={data.model.split("/").pop() || data.model}
                >
                  {data.model.split("/").pop() || data.model}
                </span>
              </>
            )}

            {data["object-class"] && (
              <>
                {(data.model || data.device) && (
                  <span className="text-gray-400">•</span>
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
        className="w-3 h-3 bg-indigo-500!"
        style={{ left: getHandleLeftPosition("gvadetect") }}
      />

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-indigo-500!"
        style={{ left: getHandleLeftPosition("gvadetect") }}
      />
    </div>
  );
};

export default GVADetectNode;
