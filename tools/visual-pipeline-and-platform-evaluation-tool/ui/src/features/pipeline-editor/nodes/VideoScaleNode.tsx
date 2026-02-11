import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const VideoScaleNode = () => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-amber-400 min-w-[220px]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-amber-100 dark:bg-amber-900 flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-amber-600 dark:text-amber-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-amber-700 dark:text-amber-300">
          VideoScale
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-amber-500!"
      style={{ left: getHandleLeftPosition("videoscale") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-amber-500!"
      style={{ left: getHandleLeftPosition("videoscale") }}
    />
  </div>
);

export default VideoScaleNode;
