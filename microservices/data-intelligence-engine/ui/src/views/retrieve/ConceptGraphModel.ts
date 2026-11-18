// Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0
import type { GraphEdge, GraphNode, GraphTrace, PoolGraph, RetrieveResult } from "@/api/console/type";

export const relationKey = (edge: GraphEdge) =>
  JSON.stringify([edge.source, edge.target, edge.relation]);

export function buildConceptGraph(
  data: PoolGraph | undefined,
  trace: GraphTrace | undefined,
  result: RetrieveResult | undefined,
  traversedOnly: boolean,
) {
  const concepts = new Map(trace?.concepts.map((node) => [node.id, node]));
  const seeds = new Set(trace?.seeds);
  const recallScores = new Map(result?.retrieved_chunks.map((chunk) => [chunk.id, chunk.score]));
  const finalChunkIds = new Set(result?.chunks.map((chunk) => chunk.id));
  const walked = new Set(trace?.edges.map(relationKey));
  const loaded = new Map(data?.nodes.map((node) => [node.id, node]));
  const traceIds = new Set([
    ...concepts.keys(), ...seeds,
    ...(trace?.edges.flatMap((edge) => [edge.source, edge.target]) || []),
  ]);
  const allNodes = new Map(loaded);
  const traceDegree = new Map<string, number>();
  for (const edge of trace?.edges || []) {
    for (const id of [edge.source, edge.target])
      traceDegree.set(id, (traceDegree.get(id) || 0) + 1);
  }
  // Traces can reference nodes outside the pool graph's pagination limit.
  for (const id of traceIds) {
    if (!allNodes.has(id)) {
      const node: GraphNode = {
        id, title: id, label: "", origin: "", degree: traceDegree.get(id) || 0,
      };
      allNodes.set(id, node);
    }
  }
  const nodes = [...allNodes.values()]
    .filter((node) => !traversedOnly || traceIds.has(node.id))
    .map((node) => {
      const concept = concepts.get(node.id);
      const seed = seeds.has(node.id);
      const recallHit = !!concept?.hit_chunk_ids.length;
      const finalResult = !!concept?.hit_chunk_ids.some((id) => finalChunkIds.has(id));
      const hitScores = (concept?.hit_chunk_ids || [])
        .map((id) => recallScores.get(id))
        .filter((score): score is number => typeof score === "number" && Number.isFinite(score));
      const score = hitScores.length ? Math.max(...hitScores) : concept?.weight;
      return { ...node, concept, seed, recallHit, finalResult, score };
    });
  const visible = new Set(nodes.map((node) => node.id));
  const allEdges = [...(data?.edges || [])];
  const knownEdges = new Set(allEdges.map(relationKey));
  for (const edge of trace?.edges || []) {
    if (!knownEdges.has(relationKey(edge))) {
      allEdges.push(edge);
      knownEdges.add(relationKey(edge));
    }
  }
  const edges = allEdges
    .map((edge, index) => ({
      ...edge,
      id: `${relationKey(edge)}:${index}`,
      traversed: walked.has(relationKey(edge)),
    }))
    .filter((edge) => visible.has(edge.source) && visible.has(edge.target) &&
      (!traversedOnly || edge.traversed));
  return {
    nodes, edges,
  };
}

export function conceptChunks(result: RetrieveResult | undefined, ids: string[]) {
  const chunks = new Map(
    [...(result?.retrieved_chunks || []), ...(result?.chunks || [])].map((chunk) => [chunk.id, chunk]),
  );
  return [...new Set(ids)].map((id) => ({ id, chunk: chunks.get(id) }));
}
