import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const Mp4MuxNode = () => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-violet-400 min-w-[220px]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-violet-100 dark:bg-violet-900 flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-violet-600 dark:text-violet-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-violet-700 dark:text-violet-300">
          Mp4Mux
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-violet-500!"
      style={{ left: getHandleLeftPosition("mp4mux") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-violet-500!"
      style={{ left: getHandleLeftPosition("mp4mux") }}
    />
  </div>
);

export default Mp4MuxNode;
