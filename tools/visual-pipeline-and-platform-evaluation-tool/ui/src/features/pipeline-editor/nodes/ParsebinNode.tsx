import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const ParsebinNode = () => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-node-role-parse-border min-w-[13.75rem]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-node-role-parse-surface flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-node-role-parse-icon"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-node-role-parse-title">
          Parsebin
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-node-role-parse-handle!"
      style={{ left: getHandleLeftPosition("parsebin") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-node-role-parse-handle!"
      style={{ left: getHandleLeftPosition("parsebin") }}
    />
  </div>
);

export default ParsebinNode;
