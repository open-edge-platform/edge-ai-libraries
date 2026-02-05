import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const QueueNode = () => (
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
            d="M4 7h16M4 12h16M4 17h16"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-sky-700 dark:text-sky-300">
          Queue
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-sky-500!"
      style={{ left: getHandleLeftPosition("queue") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-sky-500!"
      style={{ left: getHandleLeftPosition("queue") }}
    />
  </div>
);

export default QueueNode;
