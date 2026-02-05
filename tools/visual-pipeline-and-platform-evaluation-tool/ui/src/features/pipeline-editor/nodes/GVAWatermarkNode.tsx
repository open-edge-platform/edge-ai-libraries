import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

export const GVAWatermarkNodeWidth = 255;

const GVAWatermarkNode = () => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-pink-400 min-w-[255px]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-pink-100 dark:bg-pink-900 flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-pink-600 dark:text-pink-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-pink-700 dark:text-pink-300">
          GVAWatermark
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-pink-500!"
      style={{ left: getHandleLeftPosition("gvawatermark") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-pink-500!"
      style={{ left: getHandleLeftPosition("gvawatermark") }}
    />
  </div>
);

export default GVAWatermarkNode;
