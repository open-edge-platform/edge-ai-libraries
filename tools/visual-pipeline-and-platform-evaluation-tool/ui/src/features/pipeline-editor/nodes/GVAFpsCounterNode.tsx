import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

export const GVAFpsCounterNodeWidth = 255;

type GVAFpsCounterNodeProps = {
  data: {
    "starting-frame"?: number;
  };
};

const GVAFpsCounterNode = ({ data }: GVAFpsCounterNodeProps) => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-node-role-counter-border min-w-[15.9375rem]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-node-role-counter-surface flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-node-role-counter-icon"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 6V4m0 2a6 6 0 016 6h2a8 8 0 10-16 0h2a6 6 0 016-6zm-3.343 5.757l-1.414 1.415M12 12l2.828 2.828"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-node-role-counter-title">
          GVAFpsCounter
        </div>

        <div className="flex items-center gap-2 flex-wrap text-xs text-node-body-text">
          {data["starting-frame"] !== undefined && (
            <span>Start at frame: {data["starting-frame"]}</span>
          )}
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-node-role-counter-handle!"
      style={{ left: getHandleLeftPosition("gvafpscounter") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-node-role-counter-handle!"
      style={{ left: getHandleLeftPosition("gvafpscounter") }}
    />
  </div>
);

export default GVAFpsCounterNode;
