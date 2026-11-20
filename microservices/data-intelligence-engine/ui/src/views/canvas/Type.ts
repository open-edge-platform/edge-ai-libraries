// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { SourceStatus } from "@/api/console/type";

export type NodeKind = "asset" | "pool" | "source";
export interface CanvasNode {
  key: string;
  id: string;
  name: string;
  kind: NodeKind;
  resourceType: string;
  status: string;
  progressExpired?: boolean;
  validationStatus?: string;
  origin?: string;
  mediaType?: string;
  database?: string;
  collection?: string;
  assetCount?: number;
  poolCount?: number;
  sourceCount?: number;
  revision?: number;
  content?: boolean;
  error?: string;
}
export interface Position {
  x: number;
  y: number;
}
export interface CanvasEdge {
  from: string;
  to: string;
  content?: boolean;
  status?: string;
  frozen?: boolean;
  binding?: SourceStatus;
}
