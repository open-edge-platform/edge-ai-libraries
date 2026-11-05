// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { Chunk, GraphEdge, GraphNode, GraphTrace } from "@/api/console/type";

export interface ConceptFocus {
  pool: string;
  id: string;
}

export interface GraphDetailData {
  node?: GraphNode;
  concept?: GraphTrace["concepts"][number];
  edge?: GraphEdge;
  sourceName?: string;
  targetName?: string;
  citations: { id: string; chunk?: Chunk }[];
}
