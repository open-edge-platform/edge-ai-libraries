import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const VideoXRawWithDimensionsNode = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-stone-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-stone-700 dark:text-stone-300">
          video/x-raw
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-stone-100 dark:bg-stone-900 rounded">
          Caps
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        Raw video caps
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-stone-500!"
      style={{ left: getHandleLeftPosition("video/x-raw") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-stone-500!"
      style={{ left: getHandleLeftPosition("video/x-raw") }}
    />
  </div>
);

export default VideoXRawWithDimensionsNode;
