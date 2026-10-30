// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export interface TokenProviderRow {
  provider: string;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  requestCount: number | null;
  avgTokensPerRequest: number | null;
  requestShare: number | null;
  tokenShare: number | null;
  color: string;
  requestBarPercent: number;
  totalBarPercent: number;
  inputBarPercent: number;
  outputBarPercent: number;
  requestShareText: string;
  tokenShareText: string;
  inputShareText: string;
  outputShareText: string;
}

export interface LatencyProviderRow {
  provider: string;
  avgLatencyMs: number | null;
  avgTtftMs: number | null;
  avgTpotMs: number | null;
  ttftCount: number | null;
  tpotCount: number | null;
}

export interface DistributionProviderRow {
  provider: string;
  requestCount: number;
  percent: number;
  color: string;
  requestText: string;
}

export type RouterMetricRecord = Record<string, unknown>;

export interface RouterMetricsPayload {
  routing_stats?: RouterMetricRecord & {
    by_provider?: unknown;
  };
  token_metrics?: RouterMetricRecord & {
    overall?: RouterMetricRecord;
    by_provider?: unknown;
    before_router?: unknown;
    after_router?: unknown;
  };
  latency_metrics?: RouterMetricRecord & {
    overall?: RouterMetricRecord;
    by_provider?: unknown;
  };
}

export interface TokenProviderMetric {
  provider: string;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  requestCount: number | null;
  avgTokensPerRequest: number | null;
  requestShare: number | null;
  tokenShare: number | null;
}

export interface RouterTokenBreakdown {
  systemPromptTokens: number;
  toolSchemaTokens: number;
  contextTokens: number;
  overallTokens: number;
}

export interface ConfigProviderRow extends Record<string, unknown> {
  name: string;
  type?: string;
  model?: string;
  enabled?: boolean;
  fallback?: boolean;
}

export type RouterProviderDialogType = "create" | "edit";

export interface RouterProviderPayload {
  type: string;
  model: string;
  enabled: boolean;
  fallback: boolean;
  metadata: unknown;
  settings: unknown;
}

export interface ConfigPromptRow {
  idx?: number;
  model?: string;
  content?: string;
  version?: string;
  active?: boolean;
}

export type RouterPromptDialogType = "create" | "edit";

export interface RouterPromptPayload {
  model: string;
  content: string;
}

export interface RouterPromptUpdatePayload extends RouterPromptPayload {
  idx: number;
  active: boolean;
}

export interface ConfigPluginRow {
  name: string;
  node: string;
  enabled: boolean;
  trigger: "prerouting" | "postrouting" | "postresponse";
  settings: Record<string, unknown>;
  [key: string]: unknown;
}

export interface PluginNodeRow {
  node: string;
  plugin_group: string;
  description: string;
  settings_schema: Record<string, unknown>;
  [key: string]: unknown;
}

export type RouterPluginDialogType = "create" | "edit";

export interface RouterPluginPayload {
  enabled: boolean;
  trigger: ConfigPluginRow["trigger"];
  settings: Record<string, unknown>;
}

export interface PolicyConfigRow extends Record<string, unknown> {
  name: string;
  criterion: string;
  strategies: string[];
}

export type PolicyConfigDialogType = "create" | "edit";

export interface PolicyConfigPayload {
  criterion?: string;
  strategies: string[];
}

export interface StrategyConfigRow extends Record<string, unknown> {
  name: string;
}

export type StrategyConfigDialogType = "create" | "edit";

export interface StrategyConfigPayload {
  description?: string;
  rules?: unknown[];
  provider_selector: unknown;
  sort?: unknown[];
  require_healthy?: boolean;
  limit?: number | null;
}
