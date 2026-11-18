// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { normalizeNumber, normalizeNullableNumber } from "@/utils/common";
import type {
  LatencyProviderRow,
  RouterTokenBreakdown,
  TokenProviderMetric,
  TokenProviderRow,
} from "@/types/router";

const providerPalette = [
  "#2f6fed",
  "#20a162",
  "#f59e0b",
  "#8b5cf6",
  "#ef4444",
  "#64748b",
];

export const providerColor = (index: number) =>
  providerPalette[index % providerPalette.length];

export const formatCompactNumber = (value: unknown) =>
  new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(normalizeNumber(value));

export const formatMaybeCompact = (value: unknown, emptyText: string) => {
  const numberValue = Number(value);
  return Number.isFinite(numberValue)
    ? formatCompactNumber(numberValue)
    : emptyText;
};

export const formatCompactNullable = (
  value: number | null,
  emptyText: string,
) => (value === null ? emptyText : formatCompactNumber(value));

export const formatLatency = (value: unknown) =>
  `${normalizeNumber(value).toFixed(1)} ms`;

export const formatLatencyNullable = (
  value: number | null,
  emptyText: string,
) => (value === null ? emptyText : `${value.toFixed(1)} ms`);

export const formatPercent = (
  value: unknown,
  emptyText: string,
  digits = 1,
) => {
  const numberValue = Number(value);
  return Number.isFinite(numberValue)
    ? `${(numberValue * 100).toFixed(digits)}%`
    : emptyText;
};

export const formatRatioPercent = (
  value: unknown,
  emptyText: string,
  digits = 1,
) => {
  const numberValue = Number(value);
  return Number.isFinite(numberValue)
    ? `${numberValue.toFixed(digits)}%`
    : emptyText;
};

export const normalizeTokenProviderMetrics = (
  value: unknown,
): TokenProviderMetric[] => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];

  return Object.entries(value as Record<string, unknown>).map(
    ([provider, rawMetric]) => {
      const metric =
        rawMetric && typeof rawMetric === "object" && !Array.isArray(rawMetric)
          ? (rawMetric as Record<string, unknown>)
          : {};
      return {
        provider,
        inputTokens: normalizeNullableNumber(metric.input_tokens),
        outputTokens: normalizeNullableNumber(metric.output_tokens),
        totalTokens: normalizeNullableNumber(metric.total_tokens),
        requestCount: normalizeNullableNumber(metric.request_count),
        avgTokensPerRequest: normalizeNullableNumber(
          metric.avg_tokens_per_request,
        ),
        requestShare: normalizeNullableNumber(metric.request_share),
        tokenShare: normalizeNullableNumber(metric.token_share),
      };
    },
  );
};

const maxNullableValue = <T>(rows: T[], pick: (row: T) => number | null) =>
  rows.reduce(
    (maxValue, row) => Math.max(maxValue, normalizeNumber(pick(row))),
    0,
  );

const percentOfMax = (value: number | null, maxValue: number) =>
  maxValue ? Math.max((normalizeNumber(value) / maxValue) * 100, 3) : 0;

export const buildTokenProviderRows = (
  rows: TokenProviderMetric[],
  resolveColor: (row: TokenProviderMetric, index: number) => string,
  emptyText: string,
): TokenProviderRow[] => {
  const maxRequests = maxNullableValue(rows, (row) => row.requestCount);
  const maxTotalTokens = maxNullableValue(rows, (row) => row.totalTokens);
  const maxInputTokens = maxNullableValue(rows, (row) => row.inputTokens);
  const maxOutputTokens = maxNullableValue(rows, (row) => row.outputTokens);
  const totalInputTokens = rows.reduce(
    (sum, row) => sum + normalizeNumber(row.inputTokens),
    0,
  );
  const totalOutputTokens = rows.reduce(
    (sum, row) => sum + normalizeNumber(row.outputTokens),
    0,
  );

  return rows.map((row, index) => ({
    ...row,
    color: resolveColor(row, index),
    requestBarPercent: percentOfMax(row.requestCount, maxRequests),
    totalBarPercent: percentOfMax(row.totalTokens, maxTotalTokens),
    inputBarPercent: percentOfMax(row.inputTokens, maxInputTokens),
    outputBarPercent: percentOfMax(row.outputTokens, maxOutputTokens),
    requestShareText: formatPercent(row.requestShare, emptyText),
    tokenShareText: formatPercent(row.tokenShare, emptyText),
    inputShareText: totalInputTokens
      ? formatRatioPercent(
          (normalizeNumber(row.inputTokens) / totalInputTokens) * 100,
          emptyText,
        )
      : emptyText,
    outputShareText: totalOutputTokens
      ? formatRatioPercent(
          (normalizeNumber(row.outputTokens) / totalOutputTokens) * 100,
          emptyText,
        )
      : emptyText,
  }));
};

export const normalizeLatencyProviderRows = (
  value: unknown,
): LatencyProviderRow[] => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];

  return Object.entries(value as Record<string, unknown>).map(
    ([provider, rawMetric]) => {
      const metric =
        rawMetric && typeof rawMetric === "object" && !Array.isArray(rawMetric)
          ? (rawMetric as Record<string, unknown>)
          : {};
      return {
        provider,
        avgLatencyMs: normalizeNullableNumber(metric.avg_latency_ms),
        avgTtftMs: normalizeNullableNumber(metric.avg_ttft_ms),
        avgTpotMs: normalizeNullableNumber(metric.avg_tpot_ms),
        ttftCount: normalizeNullableNumber(metric.ttft_count),
        tpotCount: normalizeNullableNumber(metric.tpot_count),
      };
    },
  );
};

export const calculateCompressionDelta = (before: number, after: number) =>
  Math.max(before - after, 0);

export const calculateCompressionPercent = (before: number, after: number) =>
  before ? (calculateCompressionDelta(before, after) / before) * 100 : 0;

export const normalizeRouterTokenBreakdown = (
  value: unknown,
): RouterTokenBreakdown => {
  const metric =
    value && typeof value === "object" && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : {};
  return {
    systemPromptTokens: normalizeNumber(metric.system_prompt_tokens),
    toolSchemaTokens: normalizeNumber(metric.tool_schema_tokens),
    contextTokens: normalizeNumber(metric.context_tokens),
    overallTokens: normalizeNumber(metric.overall_tokens),
  };
};
