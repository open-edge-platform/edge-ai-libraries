import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const TeeNode = () => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-sky-400 min-w-[220px]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-sky-100 dark:bg-sky-900 flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-sky-600 dark:text-sky-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 4v7m0 0l-5 5m5-5l5 5"
          />
          <circle cx="12" cy="11" r="1.5" fill="currentColor" />
          <circle cx="7" cy="16" r="1.5" fill="currentColor" />
          <circle cx="17" cy="16" r="1.5" fill="currentColor" />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-sky-700 dark:text-sky-300">
          Tee
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-sky-500!"
      style={{ left: getHandleLeftPosition("tee") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-sky-500!"
      style={{ left: getHandleLeftPosition("tee") }}
    />
  </div>
);

export default TeeNode;
