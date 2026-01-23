import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const VideoScaleNode = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-amber-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-amber-700 dark:text-amber-300">
          VideoScale
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-amber-100 dark:bg-amber-900 rounded">
          PostProc
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        Video frame resizing element
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-amber-500!"
      style={{ left: getHandleLeftPosition("videoscale") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-amber-500!"
      style={{ left: getHandleLeftPosition("videoscale") }}
    />
  </div>
);

export default VideoScaleNode;
