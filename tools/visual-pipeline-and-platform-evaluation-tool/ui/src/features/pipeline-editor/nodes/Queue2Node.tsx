import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const Queue2Node = () => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-node-role-buffer-border min-w-[13.75rem]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-node-role-buffer-surface flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-node-role-buffer-icon"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 6h16M4 12h16M4 18h16"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-node-role-buffer-title">
          Queue2
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-node-role-buffer-handle!"
      style={{ left: getHandleLeftPosition("queue2") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-node-role-buffer-handle!"
      style={{ left: getHandleLeftPosition("queue2") }}
    />
  </div>
);

export default Queue2Node;
