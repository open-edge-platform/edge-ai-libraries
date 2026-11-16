// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };
export type ServingState = "SERVING" | "DEGRADE" | "PREPARING";

export interface Extraction {
  state: string;
  trigger: string;
  outdated?: boolean;
  next_run?: string;
  trigger_options?: JsonObject;
  active?: { not_before?: string };
  last?: {
    state: string;
    error?: string;
    finished_at?: string;
    result?: JsonObject;
  };
}
export interface SourceStatus {
  source_id: string;
  status: string;
  display_status: string;
  indexed_revision: number;
  updated_at: string;
  error?: string;
  serving_state: ServingState;
  effective_state: string;
  replaces?: string;
  extraction?: Extraction;
}
export interface Source {
  id: string;
  name: string;
  type: string;
  database_id: string;
  collection_name: string;
  operator_options: JsonObject;
  reconciled: boolean;
  reconciliation_error?: string;
  enabled: boolean;
  profile: JsonObject;
}
export interface AssetPool {
  id: string;
  name: string;
  asset_ids: string[];
  revision: number;
  source_statuses: SourceStatus[];
  metadata: JsonObject;
  display_status: string;
}
export interface Library {
  id: string;
  name: string;
  description?: string;
  default_content_source_id: string;
  content_database: string;
  asset_count: number;
  document_count: number;
  chunk_count: number;
  sources: Source[];
  asset_pools: AssetPool[];
}
export interface Asset {
  id: string;
  name: string;
  origin: string;
  kind: string;
  media_type: string;
  content_source_id: string;
  asset_pool_ids: string[];
  materialization: string | null;
}
export interface AssetPage {
  assets: Asset[];
  total: number;
}
export interface UploadResult {
  name: string;
  supported: boolean;
}
export interface IngestResult {
  library: string;
  asset_ids: string[];
  file_paths: string[];
  asset_pool_ids: string[];
  content_source_id: string;
  status: "stored" | "materializing";
}
export interface Database {
  id: string;
  type: string;
  backend: string;
  options: JsonObject;
  description: string;
  in_use_by: string[];
}
export interface DatabaseCheck {
  reachable: boolean;
  error?: string;
}
export interface BackendOption {
  database_type: string;
  backends: string[];
}
export interface ModelInfo {
  name: string;
  path?: string;
  ready: boolean;
  media?: boolean;
  supported_asset_types?: string[];
}
export interface ModelDefault {
  backend: string;
  model_id?: string;
  device?: string;
}
export interface ModelOptions {
  model_type: string;
  backend: string;
  backends: string[];
  device?: string;
  model_id?: string;
  media_model_id?: string;
  media_backend?: string;
  media_device?: string;
  api_base?: string;
  workspace?: string;
  models: ModelInfo[];
  defaults?: Record<string, ModelDefault>;
}
export interface Chunk {
  id: string;
  text: string;
  score: number;
  metadata: {
    library?: string;
    file_name?: string;
    source_id?: string;
    pool_id?: string;
    media_key?: string;
    kind?: string;
    page?: number;
    t_start_ms?: number;
    t_end_ms?: number;
    target_media?: string;
  };
}
export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
}
export interface GraphNode {
  id: string;
  title: string;
  label: string;
  degree: number;
  origin: string;
}
export interface PoolGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total: number;
  truncated: boolean;
}
export interface GraphTrace {
  asset_pool_id: string;
  seeds: string[];
  concepts: {
    id: string;
    hop: number;
    weight: number;
    hit_chunk_ids: string[];
  }[];
  edges: GraphEdge[];
}
export interface RetrieveResult {
  query: string;
  libraries: string[];
  chunks: Chunk[];
  retrieved_chunks: Chunk[];
  graph_traces?: GraphTrace[];
  postprocess_error?: string;
}
export interface RetrieveRequest {
  query: string;
  libraries: string[];
  asset_pool_ids: string[];
  top_k: number;
  retriever_type?: string;
  include_graph_trace: boolean;
  target_media: string[];
  exclude_chunk_ids: string[];
  postprocess?: {
    processor_type: string;
    top_n?: number;
    query?: string;
    reranker_model?: Record<string, string>;
  };
}
