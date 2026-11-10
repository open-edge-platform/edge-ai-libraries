// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { Library, SourceStatus } from "@/api/console/type";
import type { AssetRow } from "../assets/AssetProgress";
import type { CanvasEdge, CanvasNode, Position } from "./Type";
import { getAssetKind } from "../assets/AssetUtils";

export const NODE_WIDTH = 200;
export const NODE_HEIGHT = 92;
export const NODE_PORT_Y = 20;
export const ROW_STEP = 116;
export const COLUMN_STEP = 244;
export const CANVAS_PADDING = 24;
export const MAX_AUTO_ASSETS = 300;

const readinessOrder = [
  "failed",
  "extraction_failed",
  "indexing",
  "extracting",
  "extraction_waiting",
  "extraction_queued",
  "pending",
  "extraction_pending",
];
const isFrozen = (binding: SourceStatus) =>
  ["DEGRADE", "DISABLED"].includes(binding.effective_state);

export function buildCanvasNodes(
  library: Library,
  assets: AssetRow[],
  trackedIds: string[],
): CanvasNode[] {
  return [
    ...assets.map(
      (asset): CanvasNode => ({
        key: `asset:${asset.id}`,
        id: asset.id,
        name: asset.name || asset.id,
        kind: "asset",
        resourceType: getAssetKind(asset),
        status: asset.materialization || "unknown",
        progressExpired: asset.progressExpired,
        origin: asset.origin,
        mediaType: asset.media_type,
        poolCount: asset.asset_pool_ids.length,
      }),
    ),
    ...trackedIds
      .filter((id) => !assets.some((asset) => asset.id === id))
      .map(
        (id): CanvasNode => ({
          key: `asset:${id}`,
          id,
          name: id,
          kind: "asset",
          resourceType: "asset",
          status: "materializing",
          poolCount: 0,
        }),
      ),
    ...library.asset_pools.map(
      (pool): CanvasNode => ({
        key: `pool:${pool.id}`,
        id: pool.id,
        name: pool.name || pool.id,
        kind: "pool",
        resourceType: "pool",
        status: pool.display_status,
        assetCount: pool.asset_ids.length,
        sourceCount: pool.source_statuses.length,
        revision: pool.revision,
      }),
    ),
    ...library.sources.map((source): CanvasNode => {
      const content = source.id === library.default_content_source_id;
      const pools = library.asset_pools.filter((pool) =>
        pool.source_statuses.some((binding) => binding.source_id === source.id),
      );
      const bindings = pools.flatMap((pool) =>
        pool.source_statuses.filter(
          (binding) => binding.source_id === source.id && !isFrozen(binding),
        ),
      );
      let status = "reconciled";
      if (!source.enabled) status = "DISABLED";
      else if (!source.reconciled) status = "unreconciled";
      else if (!content && pools.length) {
        status = bindings.length
          ? readinessOrder.find((state) =>
              bindings.some((binding) => binding.display_status === state),
            ) || "ready"
          : "DEGRADE";
      }
      return {
        key: `source:${source.id}`,
        id: source.id,
        name: source.name || source.id,
        kind: "source",
        resourceType: source.type,
        status,
        validationStatus: source.reconciled ? "reconciled" : "unreconciled",
        database: source.database_id,
        collection: source.collection_name,
        poolCount: content ? library.asset_pools.length : pools.length,
        content,
        error: source.reconciliation_error,
      };
    }),
  ];
}

export function buildCanvasEdges(library: Library): CanvasEdge[] {
  return library.asset_pools.flatMap((pool) => [
    ...pool.asset_ids.map((id) => ({
      from: `asset:${id}`,
      to: `pool:${pool.id}`,
    })),
    ...pool.source_statuses
      .filter(
        (binding) => binding.source_id !== library.default_content_source_id,
      )
      .map((binding) => ({
        from: `pool:${pool.id}`,
        to: `source:${binding.source_id}`,
        status: binding.display_status,
        frozen: isFrozen(binding),
        binding,
      })),
    ...(library.default_content_source_id
      ? [
          {
            from: `pool:${pool.id}`,
            to: `source:${library.default_content_source_id}`,
            content: true,
          },
        ]
      : []),
  ]);
}

export function arrangeCanvasNodes(
  nodes: CanvasNode[],
  edges: CanvasEdge[],
): Record<string, Position> {
  const pools = nodes.filter((node) => node.kind === "pool");
  const rank = (node: CanvasNode) => {
    if (node.kind === "pool") return pools.indexOf(node);
    const index = pools.findIndex((pool) =>
      edges.some(
        (edge) =>
          (edge.from === node.key && edge.to === pool.key) ||
          (edge.to === node.key && edge.from === pool.key),
      ),
    );
    return index < 0 ? pools.length : index;
  };
  const columns = ["asset", "pool", "source"].map((kind) =>
    nodes
      .filter((node) => node.kind === kind)
      .sort((a, b) => rank(a) - rank(b)),
  );
  const maxRows = Math.max(0, ...columns.map((column) => column.length));
  const positions: Record<string, Position> = {};
  columns.forEach((column, index) =>
    column.forEach((node, row) => {
      positions[node.key] = {
        x: CANVAS_PADDING + index * COLUMN_STEP,
        y: CANVAS_PADDING + ((maxRows - column.length) / 2 + row) * ROW_STEP,
      };
    }),
  );
  return positions;
}
