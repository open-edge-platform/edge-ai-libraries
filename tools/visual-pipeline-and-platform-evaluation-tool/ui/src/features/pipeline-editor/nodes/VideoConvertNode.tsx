import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

export const VideoConvertNodeWidth = 235;

const VideoConvertNode = () => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-node-role-transform-border min-w-[14.6875rem]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-node-role-transform-surface flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-node-role-transform-icon"
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
        <div className="text-xl font-bold text-node-role-transform-title">
          VideoConvert
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-node-role-transform-handle!"
      style={{ left: getHandleLeftPosition("videoconvert") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-node-role-transform-handle!"
      style={{ left: getHandleLeftPosition("videoconvert") }}
    />
  </div>
);

export default VideoConvertNode;
