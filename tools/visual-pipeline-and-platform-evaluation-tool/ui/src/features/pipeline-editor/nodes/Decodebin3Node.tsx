import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const Decodebin3Node = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-lime-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-lime-700 dark:text-lime-300">
          Decodebin3
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-lime-100 dark:bg-lime-900 rounded">
          Decoder
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        Auto decoder bin
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-lime-500!"
      style={{ left: getHandleLeftPosition("decodebin3") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-lime-500!"
      style={{ left: getHandleLeftPosition("decodebin3") }}
    />
  </div>
);

export default Decodebin3Node;
