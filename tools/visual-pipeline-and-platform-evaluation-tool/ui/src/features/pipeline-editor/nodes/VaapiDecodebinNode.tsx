import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const VaapiDecodebinNode = () => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-lime-400 min-w-[220px]">
    <div className="flex gap-3">
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
            d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-lime-700 dark:text-lime-300">
          VaapiDecodebin
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-lime-500!"
      style={{ left: getHandleLeftPosition("vaapidecodebin") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-lime-500!"
      style={{ left: getHandleLeftPosition("vaapidecodebin") }}
    />
  </div>
);

export default VaapiDecodebinNode;
