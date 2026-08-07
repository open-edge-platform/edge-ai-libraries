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

export type ConfigProviderRow = Record<string, unknown>;

export type RouterProviderDialogType = "create" | "edit";

export interface RouterProviderPayload {
  type: string;
  model: string;
  enabled: boolean;
  metadata: unknown;
  settings: unknown;
}
