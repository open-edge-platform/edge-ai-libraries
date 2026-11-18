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

export interface CompressorTrafficMetrics {
  metrics_by_keys?: {
    provider?: Record<
      string,
      {
        "overall.total_input"?: number;
        "overall.total_output"?: number;
      }
    >;
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
  compressorTraffic: CompressorTrafficMetrics = {},
): TrafficSnapshot {
  const raw = asRecord(value) as RouterTrafficMetrics;
  const routing = raw.routing_stats ?? {};
  const tokenMetrics = raw.token_metrics ?? {};
  const requestCounts = routing.by_provider ?? {};
  const providerMetrics = tokenMetrics.by_provider ?? {};
  const compressorMetrics = compressorTraffic.metrics_by_keys?.provider ?? {};
  const providerNames = [
    ...new Set([
      ...Object.keys(requestCounts),
      ...Object.keys(providerMetrics),
    ]),
  ];
  const providers = providerNames.map((name, index) => {
    const tokens = asNumber(providerMetrics[name]?.input_tokens);
    const compression = compressorMetrics[name];
    return {
      id: `provider-${index}`,
      name,
      requests: asNumber(
        requestCounts[name] ?? providerMetrics[name]?.request_count,
      ),
      tokens,
      hasCompression: Object.prototype.hasOwnProperty.call(
        compressorMetrics,
        name,
      ),
      uncompressedTokens:
        tokens +
        asNumber(compression?.["overall.total_input"]) -
        asNumber(compression?.["overall.total_output"]),
    };
  });
  const beforeTokens =
    mode === "tokens"
      ? providers.reduce(
          (total, provider) => total + provider.uncompressedTokens,
          0,
        )
      : asNumber(tokenMetrics.before_router?.overall_tokens);
  const totalRequests =
    asNumber(routing.total_requests) ||
    providers.reduce((total, provider) => total + provider.requests, 0);
  const nodes: TrafficNode[] = [
    { id: "input", label: "Input", kind: "source", stage: 0 },
    { id: "routing", label: "Routing", kind: "router", stage: 1 },
    ...(mode === "tokens"
      ? providers
          .filter((provider) => provider.hasCompression)
          .map(
            (provider): TrafficNode => ({
              id: `token-compressor-${provider.id}`,
              label: "Token Compressor",
              kind: "plugin",
              role: "token-compressor",
              stage: 2,
            }),
          )
      : []),
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
  providers.forEach((provider) => {
    const compressorId = `token-compressor-${provider.id}`;
    const hasCompressor = mode === "tokens" && provider.hasCompression;
    if (hasCompressor) {
      edges.push({
        id: `routing-compressor-${provider.id}`,
        source: "routing",
        target: compressorId,
        requests: provider.requests,
        tokens: provider.uncompressedTokens,
      });
    }
    edges.push({
      id: `${hasCompressor ? "compressor" : "routing"}-${provider.id}`,
      source: hasCompressor ? compressorId : "routing",
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
