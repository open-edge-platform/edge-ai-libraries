// SPDX-License-Identifier: Apache-2.0
import type { PipelineNodeHandleMode } from "./PipelineNodeCard";
import { PIPELINE_NODE_ROLE_CLASSES } from "./pipelineNodeRoleClasses";

export type PipelineNodeRoleKey = keyof typeof PIPELINE_NODE_ROLE_CLASSES;

export type PipelineNodeTypeId = string;

export type PipelineNodeContract = {
  type: PipelineNodeTypeId;
  role: PipelineNodeRoleKey;
  defaultTitle: string;
  minWidthClass?: string;
  handles?: PipelineNodeHandleMode;
};
