import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const H264ParseNode = () => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-purple-400 min-w-[220px]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-purple-100 dark:bg-purple-900 flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-purple-600 dark:text-purple-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-purple-700 dark:text-purple-300">
          H264Parse
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-purple-500!"
      style={{ left: getHandleLeftPosition("h264parse") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-purple-500!"
      style={{ left: getHandleLeftPosition("h264parse") }}
    />
  </div>
);

export default H264ParseNode;
