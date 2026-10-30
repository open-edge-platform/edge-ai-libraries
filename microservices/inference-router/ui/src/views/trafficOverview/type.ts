// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export type TrafficMode = "requests" | "tokens";

interface ProviderTrafficMetrics {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  request_count?: number;
  avg_tokens_per_request?: number;
  request_share?: number;
  token_share?: number;
}

export interface RouterTrafficMetrics {
  routing_stats?: {
    total_requests?: number;
    by_provider?: Record<string, number>;
  };
  token_metrics?: {
    by_provider?: Record<string, ProviderTrafficMetrics>;
    before_router?: { overall_tokens?: number };
    after_router?: { overall_tokens?: number };
    overall?: {
      total_tokens?: number;
      total_input_tokens?: number;
      total_output_tokens?: number;
      total_requests?: number;
      avg_tokens_per_request?: number;
    };
  };
  latency_metrics?: {
    by_provider?: Record<string, Record<string, number>>;
    overall?: Record<string, number>;
  };
}

export interface TrafficNode {
  id: string;
  label: string;
  kind: string;
  role?: "token-compressor";
  stage: number;
}

export interface TrafficEdge {
  id: string;
  source: string;
  target: string;
  requests: number;
  tokens: number;
}

export interface TrafficSnapshot {
  collected_at: string;
  nodes: TrafficNode[];
  edges: TrafficEdge[];
}

const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};

const asNumber = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) ? value : 0;

export function formatRouterTraffic(
  value: unknown,
  mode: TrafficMode,
): TrafficSnapshot {
  const raw = asRecord(value) as RouterTrafficMetrics;
  const routing = raw.routing_stats ?? {};
  const tokenMetrics = raw.token_metrics ?? {};
  const requestCounts = routing.by_provider ?? {};
  const providerMetrics = tokenMetrics.by_provider ?? {};
  const providerNames = [
    ...new Set([
      ...Object.keys(requestCounts),
      ...Object.keys(providerMetrics),
    ]),
  ];
  const providers = providerNames.map((name, index) => ({
    id: `provider-${index}`,
    name,
    requests: asNumber(
      requestCounts[name] ?? providerMetrics[name]?.request_count,
    ),
    tokens: asNumber(providerMetrics[name]?.input_tokens),
  }));
  const beforeTokens = asNumber(tokenMetrics.before_router?.overall_tokens);
  const totalRequests =
    asNumber(routing.total_requests) ||
    providers.reduce((total, provider) => total + provider.requests, 0);
  const compressorNode: TrafficNode = {
    id: "token-compressor",
    label: "Token Compressor",
    kind: "plugin",
    role: "token-compressor",
    stage: 2,
  };
  const nodes: TrafficNode[] = [
    { id: "input", label: "Input", kind: "source", stage: 0 },
    { id: "routing", label: "Routing", kind: "router", stage: 1 },
    ...(mode === "tokens" ? [compressorNode] : []),
    ...providers.map((provider) => ({
      id: provider.id,
      label: provider.name,
      kind: "provider",
      stage: mode === "tokens" ? 3 : 2,
    })),
  ];
  const edges: TrafficEdge[] = [
    {
      id: "input-routing",
      source: "input",
      target: "routing",
      requests: totalRequests,
      tokens: beforeTokens,
    },
  ];
  if (mode === "tokens") {
    edges.push({
      id: "routing-compressor",
      source: "routing",
      target: "token-compressor",
      requests: totalRequests,
      tokens: beforeTokens,
    });
  }
  providers.forEach((provider) => {
    edges.push({
      id: `${mode === "tokens" ? "compressor" : "routing"}-${provider.id}`,
      source: mode === "tokens" ? "token-compressor" : "routing",
      target: provider.id,
      requests: provider.requests,
      tokens: provider.tokens,
    });
  });

  return {
    collected_at: new Date().toISOString(),
    nodes,
    edges,
  };
}

export function nodeFlow(
  snapshot: TrafficSnapshot,
  nodeId: string,
  mode: TrafficMode,
) {
  const incoming = snapshot.edges.filter((edge) => edge.target === nodeId);
  const outgoing = snapshot.edges.filter((edge) => edge.source === nodeId);
  return {
    incoming: incoming.reduce((total, edge) => total + edge[mode], 0),
    outgoing: outgoing.reduce((total, edge) => total + edge[mode], 0),
    hasIncoming: incoming.length > 0,
    hasOutgoing: outgoing.length > 0,
  };
}

export function boundaryFlow(snapshot: TrafficSnapshot, mode: TrafficMode) {
  let incoming = 0;
  let outgoing = 0;
  let compressed = 0;
  for (const node of snapshot.nodes) {
    const flow = nodeFlow(snapshot, node.id, mode);
    if (!flow.hasIncoming) incoming += flow.outgoing;
    if (!flow.hasOutgoing) outgoing += flow.incoming;
    if (node.role === "token-compressor" && mode === "tokens") {
      compressed += Math.max(0, flow.incoming - flow.outgoing);
    }
  }
  return { incoming, outgoing, compressed };
}

export const trafficLineWidth = (value: number, maximum: number) =>
  maximum > 0 && value > 0 ? Math.max(1, (value / maximum) * 28) : 1;
