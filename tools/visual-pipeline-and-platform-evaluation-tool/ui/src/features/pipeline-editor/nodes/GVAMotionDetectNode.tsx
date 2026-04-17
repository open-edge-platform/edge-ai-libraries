import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";
import { usePipelineEditorContext } from "../PipelineEditorContext.ts";

export const GVAMotionDetectNodeWidth = 280;

type GVAMotionDetectNodeProps = {
  data: {
    name?: string;
    "motion-threshold"?: number;
    "block-size"?: number;
  };
};

const GVAMotionDetectNode = ({ data }: GVAMotionDetectNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();

  return (
    <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-orange-400 min-w-[280px]">
      <div className="flex gap-3">
        <div className="shrink-0 w-10 h-10 rounded bg-orange-100 dark:bg-orange-900 flex items-center justify-center self-center">
          <svg
            className="w-6 h-6 text-orange-600 dark:text-orange-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 10V3L4 14h7v7l9-11h-7z"
            />
          </svg>
        </div>

        <div className="flex-1 flex flex-col">
          <div className="text-xl font-bold text-orange-700 dark:text-orange-300">
            {simpleGraph ? "Motion Detection" : "GVAMotionDetect"}
          </div>

          <div className="flex items-center gap-1 flex-wrap text-xs text-gray-700 dark:text-gray-300">
            {data.name && <span>{data.name}</span>}

            {data["motion-threshold"] !== undefined && (
              <>
                {data.name && <span className="text-gray-400">•</span>}
                <span>threshold: {data["motion-threshold"]}</span>
              </>
            )}

            {data["block-size"] !== undefined && (
              <>
                {(data.name || data["motion-threshold"] !== undefined) && (
                  <span className="text-gray-400">•</span>
                )}
                <span>block: {data["block-size"]}</span>
              </>
            )}
          </div>
        </div>
      </div>

      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 bg-orange-500!"
        style={{ left: getHandleLeftPosition("gvamotiondetect") }}
      />

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-orange-500!"
        style={{ left: getHandleLeftPosition("gvamotiondetect") }}
      />
    </div>
  );
};

export default GVAMotionDetectNode;
