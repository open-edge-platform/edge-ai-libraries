import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";
import type { GVA_TRACKING_TYPES } from "@/features/pipeline-editor/nodes/GVATrackNode.config.ts";
import { usePipelineEditorContext } from "../PipelineEditorContext.ts";

export type GvaTrackingType = (typeof GVA_TRACKING_TYPES)[number];

type GVATrackNodeProps = {
  data: {
    "tracking-type": GvaTrackingType;
  };
};

const GVATrackNode = ({ data }: GVATrackNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();

  return (
    <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-yellow-400 min-w-[220px]">
      <div className="flex gap-3">
        <div className="shrink-0 w-10 h-10 rounded bg-yellow-100 dark:bg-yellow-900 flex items-center justify-center self-center">
          <svg
            className="w-6 h-6 text-yellow-600 dark:text-yellow-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
            />
          </svg>
        </div>

        <div className="flex-1 flex flex-col">
          <div className="text-xl font-bold text-yellow-700 dark:text-yellow-300">
            {simpleGraph ? "Tracking" : "GVATrack"}
          </div>

          <div className="flex items-center gap-2 flex-wrap text-xs text-gray-700 dark:text-gray-300">
            {data["tracking-type"] && <span>{data["tracking-type"]}</span>}
          </div>
        </div>
      </div>

      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 bg-yellow-500!"
        style={{ left: getHandleLeftPosition("gvatrack") }}
      />

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-yellow-500!"
        style={{ left: getHandleLeftPosition("gvatrack") }}
      />
    </div>
  );
};

export default GVATrackNode;
