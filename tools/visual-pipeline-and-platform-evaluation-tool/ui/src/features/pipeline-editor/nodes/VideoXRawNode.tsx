import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const VideoXRawNode = () => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-slate-400 min-w-[220px]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-slate-100 dark:bg-slate-900 flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-slate-600 dark:text-slate-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-slate-700 dark:text-slate-300">
          Video/x-raw
        </div>

        <div className="flex items-center gap-2 flex-wrap text-xs text-gray-700 dark:text-gray-300">
          <span>VAMemory</span>
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-slate-500!"
      style={{ left: getHandleLeftPosition("video/x-raw(memory:VAMemory)") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-slate-500!"
      style={{ left: getHandleLeftPosition("video/x-raw(memory:VAMemory)") }}
    />
  </div>
);

export default VideoXRawNode;
