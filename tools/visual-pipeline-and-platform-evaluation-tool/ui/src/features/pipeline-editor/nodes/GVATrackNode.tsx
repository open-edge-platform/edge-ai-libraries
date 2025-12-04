import { Handle, Position } from "@xyflow/react";
import type { GVA_TRACKING_TYPES } from "@/features/pipeline-editor/nodes/GVATrackNode.config.ts";

export type GvaTrackingType = (typeof GVA_TRACKING_TYPES)[number];

type GVATrackNodeProps = {
  data: {
    "tracking-type": GvaTrackingType;
  };
};

const GVATrackNode = ({ data }: GVATrackNodeProps) => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-yellow-400 min-w-[200px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-yellow-700">GVATrack</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-yellow-100 rounded">
          Tracking
        </div>
      </div>

      {/* Tracking type */}
      {data["tracking-type"] && (
        <div className="text-xs text-gray-600 mb-2">
          <span className="font-medium">Tracking type:</span>
          <div className="mt-1 p-2 bg-gray-50 rounded text-xs font-mono break-all">
            {data["tracking-type"]}
          </div>
        </div>
      )}

      {/* Description */}
      <div className="text-xs text-gray-600">GStreamer VA tracking</div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Left}
      className="w-3 h-3 bg-yellow-500!"
      style={{ top: 40 }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Right}
      className="w-3 h-3 bg-yellow-500!"
      style={{ top: 40 }}
    />
  </div>
);

export default GVATrackNode;
