import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

export const GVAFpsCounterNodeWidth = 250;

const GVAFpsCounterNode = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-red-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-red-700 dark:text-red-300">
          GVAFpsCounter
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-red-100 dark:bg-red-900 rounded">
          Counter
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        GStreamer VA FPS counter
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-red-500!"
      style={{ left: getHandleLeftPosition("gvafpscounter") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-red-500!"
      style={{ left: getHandleLeftPosition("gvafpscounter") }}
    />
  </div>
);

export default GVAFpsCounterNode;
