import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";
import type { GVA_TRACKING_TYPES } from "@/features/pipeline-editor/nodes/GVATrackNode.config.ts";

export type GvaTrackingType = (typeof GVA_TRACKING_TYPES)[number];

type GVATrackNodeProps = {
  data: {
    "tracking-type": GvaTrackingType;
  };
};

const GVATrackNode = ({ data }: GVATrackNodeProps) => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-yellow-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-yellow-700 dark:text-yellow-300">
          GVATrack
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-yellow-100 dark:bg-yellow-900 rounded">
          Tracking
        </div>
      </div>

      {/* Tracking type */}
      {data["tracking-type"] && (
        <div className="text-xs text-gray-600 dark:text-gray-300 mb-2">
          <span className="font-medium">Tracking type:</span>
          <div className="mt-1 p-2 bg-gray-50 dark:bg-gray-800 rounded text-xs font-mono break-all">
            {data["tracking-type"]}
          </div>
        </div>
      )}

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        GStreamer VA tracking
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-yellow-500!"
      style={{ left: getHandleLeftPosition("gvatrack") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-yellow-500!"
      style={{ left: getHandleLeftPosition("gvatrack") }}
    />
  </div>
);

export default GVATrackNode;
