import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

export const GVAWatermarkNodeWidth = 243;

const GVAWatermarkNode = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-pink-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-pink-700 dark:text-pink-300">
          GVAWatermark
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-pink-100 dark:bg-pink-900 rounded">
          Overlay
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        GStreamer VA watermark
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-pink-500!"
      style={{ left: getHandleLeftPosition("gvawatermark") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-pink-500!"
      style={{ left: getHandleLeftPosition("gvawatermark") }}
    />
  </div>
);

export default GVAWatermarkNode;
