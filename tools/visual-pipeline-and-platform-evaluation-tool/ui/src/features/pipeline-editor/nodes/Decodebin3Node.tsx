import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const Decodebin3Node = () => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-lime-400 min-w-[220px]">
    <div className="flex gap-3">
      {/* Icon - spans both rows */}
      <div className="shrink-0 w-10 h-10 rounded bg-lime-100 dark:bg-lime-900 flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-lime-600 dark:text-lime-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      </div>

      {/* Content - Name and Properties */}
      <div className="flex-1 flex flex-col">
        {/* Name */}
        <div className="text-xl font-bold text-lime-700 dark:text-lime-300">
          Decodebin3
        </div>

        {/* Properties */}
        <div className="flex items-center gap-2 flex-wrap text-xs text-gray-700 dark:text-gray-300">
          <span></span>
        </div>
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
