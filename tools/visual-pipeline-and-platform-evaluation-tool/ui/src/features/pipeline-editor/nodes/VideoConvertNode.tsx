import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

export const VideoConvertNodeWidth = 235;

const VideoConvertNode = () => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-amber-400 min-w-[235px]">
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
            d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-amber-700 dark:text-amber-300">
          VideoConvert
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-amber-500!"
      style={{ left: getHandleLeftPosition("videoconvert") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-amber-500!"
      style={{ left: getHandleLeftPosition("videoconvert") }}
    />
  </div>
);

export default VideoConvertNode;
