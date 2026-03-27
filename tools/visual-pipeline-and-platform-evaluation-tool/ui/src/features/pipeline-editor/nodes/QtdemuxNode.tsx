import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const QtdemuxNode = () => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-node-role-demux-border min-w-[13.75rem]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-node-role-demux-surface flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-node-role-demux-icon"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-node-role-demux-title">
          QtDemux
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-node-role-demux-handle!"
      style={{ left: getHandleLeftPosition("qtdemux") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-node-role-demux-handle!"
      style={{ left: getHandleLeftPosition("qtdemux") }}
    />
  </div>
);

export default QtdemuxNode;
