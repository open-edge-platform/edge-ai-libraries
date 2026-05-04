// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import { Handle, Position } from "@xyflow/react";
import type { PipelineNodeRoleClasses } from "./pipelineNodeRoleClasses";

export type PipelineNodeHandleMode = "both" | "target" | "source" | "none";

export type PipelineNodeCardProps = {
  title: ReactNode;
  icon: ReactNode;
  nodeType: string;
  roleClasses: PipelineNodeRoleClasses;
  details?: ReactNode;
  minWidthClass?: string;
  handles?: PipelineNodeHandleMode;
};

const PipelineNodeCard = ({
  title,
  icon,
  nodeType: _nodeType,
  roleClasses,
  details,
  minWidthClass = "min-w-[13.75rem]",
  handles = "both",
}: PipelineNodeCardProps) => (
  <div
    className={`p-4 rounded shadow-md bg-background border border-l-4 ${roleClasses.color} ${roleClasses.border} ${minWidthClass}`}
  >
    <div className="flex gap-3">
      <div
        className={`shrink-0 w-10 h-10 rounded ${roleClasses.surface} flex items-center justify-center self-center`}
      >
        <svg
          className={`w-6 h-6 ${roleClasses.icon}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          {icon}
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className={`text-xl font-bold ${roleClasses.title}`}>{title}</div>
        {details}
      </div>
    </div>

    {(handles === "both" || handles === "target") && (
      <Handle
        type="target"
        position={Position.Top}
        className={`w-3 h-3 ${roleClasses.handle}`}
      />
    )}

    {(handles === "both" || handles === "source") && (
      <Handle
        type="source"
        position={Position.Bottom}
        className={`w-3 h-3 ${roleClasses.handle}`}
      />
    )}
  </div>
);

export default PipelineNodeCard;
