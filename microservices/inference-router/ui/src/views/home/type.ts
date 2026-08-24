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

export interface RouterOverviewDrawerData {
  distributionProviderRows: DistributionProviderRow[];
  tokenProviderRows: TokenProviderRow[];
  totalRequestsText: string;
  totalTokensText: string;
  totalInputTokens: number;
  totalOutputTokens: number;
  latencyProviderRows: LatencyProviderRow[];
  avgLatencyMs: number | null;
  beforeRouterTokensText: string;
  afterRouterTokensText: string;
  routerCompressedTokensText: string;
  routerCompressionPercent: number;
  routerCompressionPercentText: string;
  routerCompressionRestPercent: number;
  routerCompressionRestPercentText: string;
  systemPromptBeforeTokensText: string;
  systemPromptAfterTokensText: string;
  systemPromptCompressedTokensText: string;
  systemPromptCompressionPercent: number;
  systemPromptCompressionPercentText: string;
  toolSchemaBeforeTokensText: string;
  toolSchemaAfterTokensText: string;
  toolSchemaCompressedTokensText: string;
  toolSchemaCompressionPercent: number;
  toolSchemaCompressionPercentText: string;
  contextBeforeTokensText: string;
  contextAfterTokensText: string;
  contextCompressedTokensText: string;
  contextCompressionPercent: number;
  contextCompressionPercentText: string;
  avgTtftMs: number | null;
  avgTpotMs: number | null;
  isMetricsRefreshing: boolean;
  isResetting: boolean;
}

export type ConfigProviderRow = Record<string, unknown>;

export type RouterProviderDialogType = "create" | "edit";

export interface RouterProviderPayload {
  type: string;
  model: string;
  enabled: boolean;
  metadata: unknown;
  settings: unknown;
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

export type PolicyConfigRow = Record<string, unknown>;

export type PolicyConfigDialogType = "create" | "edit";

export interface PolicyConfigPayload {
  criterion?: string;
  strategies: string[];
}

export type StrategyConfigRow = Record<string, unknown>;

export type StrategyConfigDialogType = "create" | "edit";

export interface StrategyConfigPayload {
  description?: string;
  rules?: unknown[];
  provider_selector: unknown;
  sort?: unknown[];
  require_healthy?: boolean;
  limit?: number | null;
}
