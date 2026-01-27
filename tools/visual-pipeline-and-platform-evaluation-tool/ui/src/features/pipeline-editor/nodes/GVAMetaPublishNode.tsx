import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

export const GVAMetaPublishNodeWidth = 268;

const GVAMetaPublishNode = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-emerald-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-emerald-700 dark:text-emerald-300">
          GVAMetaPublish
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-emerald-100 dark:bg-emerald-900 rounded">
          Publisher
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        GStreamer VA meta publisher
      </div>
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
