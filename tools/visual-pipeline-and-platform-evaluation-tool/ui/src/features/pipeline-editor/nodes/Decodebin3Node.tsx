import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const Decodebin3Node = () => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-node-role-decode-border min-w-[13.75rem]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-node-role-decode-surface flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-node-role-decode-icon"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-node-role-decode-title">
          Decodebin3
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-node-role-decode-handle!"
      style={{ left: getHandleLeftPosition("decodebin3") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-node-role-decode-handle!"
      style={{ left: getHandleLeftPosition("decodebin3") }}
    />
  </div>
);

export default Decodebin3Node;
