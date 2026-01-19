import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

export const GVAMetaPublishNodeWidth = 250;

const GVAMetaPublishNode = () => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-emerald-400 min-w-[200px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-emerald-700">GVAMetaPublish</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-emerald-100 rounded">
          Publisher
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600">GStreamer VA meta publisher</div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-emerald-500!"
      style={{ left: getHandleLeftPosition("gvametapublish") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-emerald-500!"
      style={{ left: getHandleLeftPosition("gvametapublish") }}
    />
  </div>
);

export default GVAMetaPublishNode;
