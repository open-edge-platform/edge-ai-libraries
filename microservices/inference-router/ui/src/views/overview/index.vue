<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <section
    ref="overviewRootRef"
    class="router-detail-module router-overview-module"
    role="tabpanel"
  >
    <div class="router-module-heading">
      <span class="section-icon"><FundOutlined /></span>
      <div>
        <div class="section-title">{{ t("router.OverviewTab") }}</div>
        <div class="section-caption">
          {{ t("router.routerOverviewCaption") }}
        </div>
      </div>
      <div class="router-module-actions">
        <a-button
          type="text"
          shape="circle"
          size="small"
          :title="t('router.refresh')"
          :loading="isMetricsRefreshing"
          @click="handleRefreshMetrics"
        >
          <template #icon><ReloadOutlined /></template>
        </a-button>
        <a-button
          type="text"
          shape="circle"
          size="small"
          danger
          :title="t('common.reset')"
          :loading="isResetting"
          @click="handleResetMetrics"
        >
          <template #icon><RedoOutlined /></template>
        </a-button>
      </div>
    </div>

    <div class="router-overview-grid">
      <section class="router-overview-card request-overview-card">
        <div class="overview-card-heading">
          <span class="overview-card-icon request-icon">
            <PieChartOutlined />
          </span>
          <div class="overview-card-copy">
            <h3>{{ t("router.routerRequestShare") }}</h3>
            <p>{{ t("router.routerProviderDistributionCaption") }}</p>
          </div>
          <div class="overview-card-total">
            <span>{{ t("router.routerOverallLabel") }}</span>
            <strong>{{ totalRequestsText }}</strong>
          </div>
        </div>

        <div class="request-card-content">
          <VChart
            ref="requestPieChartRef"
            class="overview-pie-chart request-pie-chart"
            :option="requestPieOption"
            autoresize
          />
          <div class="overview-provider-legend">
            <div
              v-for="item in requestLegendRows"
              :key="`request-${item.provider}`"
              class="overview-provider-row"
            >
              <span
                class="router-dot"
                :style="{ background: item.color }"
              ></span>
              <span class="overview-provider-name">{{ item.provider }}</span>
              <strong>{{ item.percentText }}</strong>
              <small>{{ item.valueText }}</small>
            </div>
          </div>
        </div>
      </section>
      <section class="router-overview-card token-overview-card">
        <div class="overview-card-heading">
          <span class="overview-card-icon-group" aria-hidden="true">
            <span class="overview-card-icon token-icon">
              <DatabaseOutlined />
            </span>
          </span>
          <div class="overview-card-copy">
            <h3>{{ t("router.routerTokenShare") }}</h3>
            <p>{{ t("router.routerTokenShareCaption") }}</p>
          </div>
          <div class="overview-card-total">
            <span>{{ t("router.routerOverallLabel") }}</span>
            <strong>{{ totalTokensText }}</strong>
          </div>
        </div>
        <div class="token-card-content">
          <div class="token-share-pane token-chart-pane">
            <div class="overview-chart-heading">
              <span>{{ t("router.providerTokenShare") }}</span>
              <small>{{ totalTokensText }}</small>
            </div>
            <VChart
              ref="tokenPieChartRef"
              class="overview-pie-chart token-pie-chart"
              :option="tokenPieOption"
              autoresize
            />
            <div class="overview-provider-legend token-provider-legend">
              <div
                v-for="item in tokenLegendRows"
                :key="`token-${item.provider}`"
                class="overview-provider-row"
              >
                <span
                  class="router-dot"
                  :style="{ background: item.color }"
                ></span>
                <span class="overview-provider-name" :title="item.provider">{{
                  item.provider
                }}</span>
                <strong>{{ item.percentText }}</strong>
                <small class="overview-provider-value">{{
                  item.valueText
                }}</small>
              </div>
            </div>
          </div>

          <div class="token-input-output-pane token-chart-pane">
            <div class="overview-chart-heading">
              <span>{{ t("router.routerInputOutputShare") }}</span>
              <small>{{ t("router.routerProviderComparisonTitle") }}</small>
            </div>
            <template v-if="inputOutputSeriesRows.length">
              <VChart
                ref="inputOutputBarChartRef"
                class="input-output-bar-chart"
                :option="inputOutputBarOption"
                autoresize
              />
              <div class="provider-inline-legend">
                <span
                  v-for="item in inputOutputSeriesRows"
                  :key="`io-legend-${item.provider}`"
                  class="provider-inline-legend-item"
                >
                  <span
                    class="router-dot"
                    :style="{ background: item.color }"
                  ></span>
                  <span class="provider-inline-name">{{ item.provider }}</span>
                </span>
              </div>
            </template>
            <div v-else class="overview-nodata-center compact">
              <NoData />
            </div>
          </div>
        </div>
      </section>

      <section class="router-overview-card compression-overview-card">
        <div class="overview-card-heading">
          <span class="overview-card-icon compression-icon">
            <LineChartOutlined />
          </span>
          <div class="overview-card-copy">
            <h3>{{ t("router.routerCompressionTitle") }}</h3>
            <p>
              {{
                t("router.routerCompressionCaption", {
                  percent: routerCompressionPercentText,
                })
              }}
            </p>
          </div>
          <div class="compression-saved-stat">
            <strong>{{ routerCompressionPercentText }}</strong>
            <span>{{ routerCompressedTokensText }}</span>
          </div>
        </div>

        <div class="restored-compression-content">
          <div class="router-consumption-summary">
            <div class="router-summary-main">
              <div class="router-summary-wrap">
                <span class="router-summary-title">{{
                  t("router.routerOverallLabel")
                }}</span>
                <div class="router-summary-copy">
                  <span class="router-summary-copy-label">
                    {{ t("router.inboundTokens") }}
                  </span>
                  <span class="router-summary-copy-value">
                    {{ beforeRouterTokensText }}
                  </span>
                </div>
                <div class="router-stack-track">
                  <a-tooltip
                    placement="top"
                    :title="`${t('router.outboundTokens')}: ${afterRouterTokensText}`"
                  >
                    <span
                      class="router-segment-tooltip"
                      :style="{ width: `${routerRemainingRatio}%` }"
                    >
                      <span class="router-stack-segment router-consumed"></span>
                    </span>
                  </a-tooltip>
                  <a-tooltip
                    placement="top"
                    :title="`${t('router.routerCompressedTokens')}: ${routerCompressedTokensText}`"
                  >
                    <span
                      class="router-segment-tooltip"
                      :style="{ width: `${routerCompressionPercent}%` }"
                    >
                      <span class="router-stack-segment router-saved"></span>
                    </span>
                  </a-tooltip>
                </div>
              </div>
              <div class="router-summary-breakdown">
                <div class="router-breakdown-row router-consumption-row">
                  <span class="router-breakdown-main">
                    <span class="router-dot consumed"></span>
                    <span>{{ t("router.outboundTokens") }}</span>
                  </span>
                  <span>{{ routerCompressionRestPercentText }}</span>
                  <strong>{{ afterRouterTokensText }}</strong>
                </div>
                <div class="router-breakdown-row router-saved-row">
                  <span class="router-breakdown-main">
                    <span class="router-dot saved"></span>
                    <span>{{ t("router.routerCompressedTokens") }}</span>
                  </span>
                  <span>{{ routerCompressionPercentText }}</span>
                  <strong>{{ routerCompressedTokensText }}</strong>
                </div>
              </div>
            </div>
          </div>

          <div class="router-breakdown-grid">
            <article class="router-breakdown-card tone-system">
              <div class="router-breakdown-card-head">
                <span class="router-breakdown-card-label">
                  {{ t("router.routerSystemPromptTokens") }}
                </span>
                <div class="router-summary-copy">
                  <span class="router-summary-copy-label">
                    {{ t("router.inboundTokens") }}
                  </span>
                  <span class="router-summary-copy-value">
                    {{ systemPromptBeforeTokensText }}
                  </span>
                </div>
              </div>
              <div class="router-breakdown-bar-track">
                <a-tooltip
                  placement="top"
                  :title="`${t('router.outboundTokens')}: ${systemPromptAfterTokensText}`"
                >
                  <span
                    class="router-segment-tooltip"
                    :style="{ width: `${systemPromptRemainingPercent}%` }"
                  >
                    <span class="router-breakdown-bar consumed"></span>
                  </span>
                </a-tooltip>
                <a-tooltip
                  placement="top"
                  :title="`${t('router.routerCompressedTokens')}: ${systemPromptCompressedTokensText}`"
                >
                  <span
                    class="router-segment-tooltip"
                    :style="{ width: `${systemPromptCompressionPercent}%` }"
                  >
                    <span class="router-breakdown-bar saved"></span>
                  </span>
                </a-tooltip>
              </div>
              <div class="router-breakdown-card-metrics">
                <div class="router-breakdown-metric">
                  <span class="saved-label">{{
                    t("router.outboundTokens")
                  }}</span>
                  <span class="saved-value">
                    {{ systemPromptAfterTokensText }}
                  </span>
                </div>
                <div class="router-breakdown-metric saved">
                  <span class="saved-label">
                    {{ t("router.routerCompressedTokens") }}
                  </span>
                  <span class="saved-value">
                    {{ systemPromptCompressedTokensText }}
                    <span class="saved-value-percent">
                      ({{ systemPromptCompressionPercentText }})
                    </span>
                  </span>
                </div>
              </div>
            </article>

            <article class="router-breakdown-card tone-tool">
              <div class="router-breakdown-card-head">
                <span class="router-breakdown-card-label">
                  {{ t("router.routerToolSchemaTokens") }}
                </span>
                <div class="router-summary-copy">
                  <span class="router-summary-copy-label">
                    {{ t("router.inboundTokens") }}
                  </span>
                  <span class="router-summary-copy-value">
                    {{ toolSchemaBeforeTokensText }}
                  </span>
                </div>
              </div>
              <div class="router-breakdown-bar-track">
                <a-tooltip
                  placement="top"
                  :title="`${t('router.outboundTokens')}: ${toolSchemaAfterTokensText}`"
                >
                  <span
                    class="router-segment-tooltip"
                    :style="{ width: `${toolSchemaRemainingPercent}%` }"
                  >
                    <span class="router-breakdown-bar consumed"></span>
                  </span>
                </a-tooltip>
                <a-tooltip
                  placement="top"
                  :title="`${t('router.routerCompressedTokens')}: ${toolSchemaCompressedTokensText}`"
                >
                  <span
                    class="router-segment-tooltip"
                    :style="{ width: `${toolSchemaCompressionPercent}%` }"
                  >
                    <span class="router-breakdown-bar saved"></span>
                  </span>
                </a-tooltip>
              </div>
              <div class="router-breakdown-card-metrics">
                <div class="router-breakdown-metric">
                  <span class="saved-label">{{
                    t("router.outboundTokens")
                  }}</span>
                  <span class="saved-value">
                    {{ toolSchemaAfterTokensText }}
                  </span>
                </div>
                <div class="router-breakdown-metric saved">
                  <span class="saved-label">
                    {{ t("router.routerCompressedTokens") }}
                  </span>
                  <span class="saved-value">
                    {{ toolSchemaCompressedTokensText }}
                    <span class="saved-value-percent">
                      ({{ toolSchemaCompressionPercentText }})
                    </span>
                  </span>
                </div>
              </div>
            </article>

            <article class="router-breakdown-card tone-context">
              <div class="router-breakdown-card-head">
                <span class="router-breakdown-card-label">
                  {{ t("router.routerContextTokens") }}
                </span>
                <div class="router-summary-copy">
                  <span class="router-summary-copy-label">
                    {{ t("router.inboundTokens") }}
                  </span>
                  <span class="router-summary-copy-value">
                    {{ contextBeforeTokensText }}
                  </span>
                </div>
              </div>
              <div class="router-breakdown-bar-track">
                <a-tooltip
                  placement="top"
                  :title="`${t('router.outboundTokens')}: ${contextAfterTokensText}`"
                >
                  <span
                    class="router-segment-tooltip"
                    :style="{ width: `${contextRemainingPercent}%` }"
                  >
                    <span class="router-breakdown-bar consumed"></span>
                  </span>
                </a-tooltip>
                <a-tooltip
                  placement="top"
                  :title="`${t('router.routerCompressedTokens')}: ${contextCompressedTokensText}`"
                >
                  <span
                    class="router-segment-tooltip"
                    :style="{ width: `${contextCompressionPercent}%` }"
                  >
                    <span class="router-breakdown-bar saved"></span>
                  </span>
                </a-tooltip>
              </div>
              <div class="router-breakdown-card-metrics">
                <div class="router-breakdown-metric">
                  <span class="saved-label">{{
                    t("router.outboundTokens")
                  }}</span>
                  <span class="saved-value">
                    {{ contextAfterTokensText }}
                  </span>
                </div>
                <div class="router-breakdown-metric saved">
                  <span class="saved-label">
                    {{ t("router.routerCompressedTokens") }}
                  </span>
                  <span class="saved-value">
                    {{ contextCompressedTokensText }}
                    <span class="saved-value-percent">
                      ({{ contextCompressionPercentText }})
                    </span>
                  </span>
                </div>
              </div>
            </article>
          </div>
        </div>
      </section>

      <section class="router-overview-card latency-overview-card">
        <div class="overview-card-heading">
          <span class="overview-card-icon latency-icon">
            <ClockCircleOutlined />
          </span>
          <div class="overview-card-copy">
            <h3>{{ t("router.routerLatencyOverallTitle") }}</h3>
            <p>
              <span>{{ t("router.routerLatencyQuickCaption") }}</span>
              <span class="latency-caption-highlight">{{
                t("router.routerLatencyQuickCaptionHighlight")
              }}</span>
            </p>
          </div>
        </div>

        <div class="latency-card-content">
          <VChart
            v-if="latencyProviderSeriesRows.length"
            ref="latencyComparisonChartRef"
            class="latency-comparison-chart"
            :option="latencyComparisonOption"
            autoresize
          />
          <div v-else class="overview-nodata-center">
            <NoData />
          </div>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  computed,
  createVNode,
  nextTick,
  onMounted,
  onUnmounted,
  ref,
  watch,
} from "vue";
import { useI18n } from "vue-i18n";
import { Modal } from "ant-design-vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import type { EChartsType } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { BarChart, PieChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import {
  ClockCircleOutlined,
  DatabaseOutlined,
  LineChartOutlined,
  PieChartOutlined,
  RedoOutlined,
  ReloadOutlined,
  FundOutlined,
  ExclamationCircleFilled,
} from "@ant-design/icons-vue";
import { getRouterMetrics, resetRouterMetrics } from "@/api/overview";
import { normalizeNumber, normalizeNullableNumber } from "@/utils/common";
import {
  buildTokenProviderRows,
  calculateCompressionDelta,
  calculateCompressionPercent,
  formatCompactNullable,
  formatCompactNumber,
  formatMaybeCompact,
  formatRatioPercent,
  normalizeLatencyProviderRows,
  normalizeRouterTokenBreakdown,
  normalizeTokenProviderMetrics,
  providerColor,
} from "@/utils/routerMetrics";
import type {
  DistributionProviderRow,
  RouterMetricsPayload,
  TokenProviderRow,
} from "@/types/router";

use([
  CanvasRenderer,
  PieChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
]);

const { t } = useI18n();
const metricsPayload = ref<RouterMetricsPayload>({});
const isMetricsRefreshing = ref(false);
const isResetting = ref(false);
const emptyValueText = computed(() => t("router.routerEmptyValue"));
const routingStats = computed(() => metricsPayload.value.routing_stats ?? {});
const tokenMetrics = computed(() => metricsPayload.value.token_metrics ?? {});
const tokenOverall = computed(() => tokenMetrics.value.overall ?? {});
const latencyMetrics = computed(
  () => metricsPayload.value.latency_metrics ?? {},
);
const latencyOverall = computed(() => latencyMetrics.value.overall ?? {});
const tokenProviderMetrics = computed(() =>
  normalizeTokenProviderMetrics(tokenMetrics.value.by_provider),
);
const latencyProviderRows = computed(() =>
  normalizeLatencyProviderRows(latencyMetrics.value.by_provider),
);
const totalRequests = computed(() =>
  normalizeNumber(routingStats.value.total_requests),
);

interface DistributionMetricRow {
  provider: string;
  requestCount: number;
}

const buildDistributionRows = (
  rows: DistributionMetricRow[],
  resolveColor: (provider: string, index: number) => string,
): DistributionProviderRow[] => {
  const providerTotal = rows.reduce((sum, row) => sum + row.requestCount, 0);
  const requestTotal = providerTotal || totalRequests.value;

  return rows.map((row, index) => {
    const percent = requestTotal ? (row.requestCount / requestTotal) * 100 : 0;
    return {
      provider: row.provider,
      requestCount: row.requestCount,
      percent,
      color: resolveColor(row.provider, index),
      requestText: `${formatCompactNumber(row.requestCount)} (${percent.toFixed(1)}%)`,
    };
  });
};

const buildDistributionFallbackRows = (
  rows: TokenProviderRow[],
  resolveColor: (provider: string, index: number) => string,
): DistributionProviderRow[] =>
  rows
    .filter((row) => normalizeNumber(row.requestCount) > 0)
    .map((row, index) => ({
      provider: row.provider,
      requestCount: normalizeNumber(row.requestCount),
      percent: normalizeNumber(row.requestShare) * 100,
      color: resolveColor(row.provider, index),
      requestText: `${formatCompactNullable(row.requestCount, emptyValueText.value)} (${(normalizeNumber(row.requestShare) * 100).toFixed(1)}%)`,
    }));

const overviewProviderOrder = computed(() => {
  if (tokenProviderMetrics.value.length) {
    return tokenProviderMetrics.value.map((row) => row.provider);
  }

  const routingByProvider = routingStats.value.by_provider;
  if (
    routingByProvider &&
    typeof routingByProvider === "object" &&
    !Array.isArray(routingByProvider)
  ) {
    return Object.keys(routingByProvider as Record<string, unknown>);
  }

  const latencyByProvider = latencyMetrics.value.by_provider;
  if (
    latencyByProvider &&
    typeof latencyByProvider === "object" &&
    !Array.isArray(latencyByProvider)
  ) {
    return Object.keys(latencyByProvider as Record<string, unknown>);
  }

  return [];
});
const overviewProviderColorMap = computed(() => {
  const colorMap = new Map<string, string>();
  overviewProviderOrder.value.forEach((provider, index) => {
    colorMap.set(provider, providerColor(index));
  });
  return colorMap;
});
const overviewProviderColor = (provider: string, fallbackIndex: number) =>
  overviewProviderColorMap.value.get(provider) ?? providerColor(fallbackIndex);
const tokenProviderRows = computed(() =>
  buildTokenProviderRows(
    [...tokenProviderMetrics.value],
    (row, index) => overviewProviderColor(row.provider, index),
    emptyValueText.value,
  ),
);
const distributionProviderRows = computed<DistributionProviderRow[]>(() => {
  const byProvider = routingStats.value.by_provider;
  if (
    byProvider &&
    typeof byProvider === "object" &&
    !Array.isArray(byProvider)
  ) {
    const rows = Object.entries(byProvider as Record<string, unknown>)
      .map(([provider, count]) => ({
        provider,
        requestCount: normalizeNumber(count),
      }))
      .filter((row) => row.requestCount > 0);
    return buildDistributionRows(rows, overviewProviderColor);
  }

  return buildDistributionFallbackRows(
    tokenProviderRows.value,
    overviewProviderColor,
  );
});

const beforeRouterTokens = computed(() =>
  normalizeRouterTokenBreakdown(tokenMetrics.value.before_router),
);
const afterRouterTokens = computed(() =>
  normalizeRouterTokenBreakdown(tokenMetrics.value.after_router),
);
const routerCompressedTokens = computed(() =>
  calculateCompressionDelta(
    beforeRouterTokens.value.overallTokens,
    afterRouterTokens.value.overallTokens,
  ),
);
const routerCompressionPercentValue = computed(() =>
  calculateCompressionPercent(
    beforeRouterTokens.value.overallTokens,
    afterRouterTokens.value.overallTokens,
  ),
);
const routerCompressionRestPercentValue = computed(() =>
  beforeRouterTokens.value.overallTokens
    ? (afterRouterTokens.value.overallTokens /
        beforeRouterTokens.value.overallTokens) *
      100
    : 0,
);
const systemPromptCompressionValue = computed(() =>
  calculateCompressionPercent(
    beforeRouterTokens.value.systemPromptTokens,
    afterRouterTokens.value.systemPromptTokens,
  ),
);
const toolSchemaCompressionValue = computed(() =>
  calculateCompressionPercent(
    beforeRouterTokens.value.toolSchemaTokens,
    afterRouterTokens.value.toolSchemaTokens,
  ),
);
const contextCompressionValue = computed(() =>
  calculateCompressionPercent(
    beforeRouterTokens.value.contextTokens,
    afterRouterTokens.value.contextTokens,
  ),
);

const totalRequestsText = computed(() =>
  formatCompactNumber(routingStats.value.total_requests),
);
const totalTokensText = computed(() =>
  formatMaybeCompact(tokenOverall.value.total_tokens, emptyValueText.value),
);
const totalInputTokens = computed(() =>
  normalizeNumber(tokenOverall.value.total_input_tokens),
);
const totalOutputTokens = computed(() =>
  normalizeNumber(tokenOverall.value.total_output_tokens),
);
const avgLatencyMs = computed(() =>
  normalizeNullableNumber(latencyOverall.value.avg_latency_ms),
);
const avgTtftMs = computed(() =>
  normalizeNullableNumber(latencyOverall.value.avg_ttft_ms),
);
const avgTpotMs = computed(() =>
  normalizeNullableNumber(latencyOverall.value.avg_tpot_ms),
);
const beforeRouterTokensText = computed(() =>
  formatMaybeCompact(
    beforeRouterTokens.value.overallTokens,
    emptyValueText.value,
  ),
);
const afterRouterTokensText = computed(() =>
  formatMaybeCompact(
    afterRouterTokens.value.overallTokens,
    emptyValueText.value,
  ),
);
const routerCompressedTokensText = computed(() =>
  formatMaybeCompact(routerCompressedTokens.value, emptyValueText.value),
);
const routerCompressionPercentText = computed(() =>
  formatRatioPercent(routerCompressionPercentValue.value, emptyValueText.value),
);
const routerCompressionRestPercentText = computed(() =>
  formatRatioPercent(
    routerCompressionRestPercentValue.value,
    emptyValueText.value,
  ),
);
const systemPromptBeforeTokensText = computed(() =>
  formatMaybeCompact(
    beforeRouterTokens.value.systemPromptTokens,
    emptyValueText.value,
  ),
);
const systemPromptAfterTokensText = computed(() =>
  formatMaybeCompact(
    afterRouterTokens.value.systemPromptTokens,
    emptyValueText.value,
  ),
);
const systemPromptCompressedTokensText = computed(() =>
  formatMaybeCompact(
    calculateCompressionDelta(
      beforeRouterTokens.value.systemPromptTokens,
      afterRouterTokens.value.systemPromptTokens,
    ),
    emptyValueText.value,
  ),
);
const systemPromptCompressionPercentText = computed(() =>
  formatRatioPercent(systemPromptCompressionValue.value, emptyValueText.value),
);
const toolSchemaBeforeTokensText = computed(() =>
  formatMaybeCompact(
    beforeRouterTokens.value.toolSchemaTokens,
    emptyValueText.value,
  ),
);
const toolSchemaAfterTokensText = computed(() =>
  formatMaybeCompact(
    afterRouterTokens.value.toolSchemaTokens,
    emptyValueText.value,
  ),
);
const toolSchemaCompressedTokensText = computed(() =>
  formatMaybeCompact(
    calculateCompressionDelta(
      beforeRouterTokens.value.toolSchemaTokens,
      afterRouterTokens.value.toolSchemaTokens,
    ),
    emptyValueText.value,
  ),
);
const toolSchemaCompressionPercentText = computed(() =>
  formatRatioPercent(toolSchemaCompressionValue.value, emptyValueText.value),
);
const contextBeforeTokensText = computed(() =>
  formatMaybeCompact(
    beforeRouterTokens.value.contextTokens,
    emptyValueText.value,
  ),
);
const contextAfterTokensText = computed(() =>
  formatMaybeCompact(
    afterRouterTokens.value.contextTokens,
    emptyValueText.value,
  ),
);
const contextCompressedTokensText = computed(() =>
  formatMaybeCompact(
    calculateCompressionDelta(
      beforeRouterTokens.value.contextTokens,
      afterRouterTokens.value.contextTokens,
    ),
    emptyValueText.value,
  ),
);
const contextCompressionPercentText = computed(() =>
  formatRatioPercent(contextCompressionValue.value, emptyValueText.value),
);

const overviewRootRef = ref<HTMLElement | null>(null);
const requestPieChartRef = ref<{ chart: EChartsType | null } | null>(null);
const tokenPieChartRef = ref<{ chart: EChartsType | null } | null>(null);
const inputOutputBarChartRef = ref<{ chart: EChartsType | null } | null>(null);
const latencyComparisonChartRef = ref<{ chart: EChartsType | null } | null>(
  null,
);

let resizeObserver: ResizeObserver | null = null;
let resizeRafId: number | null = null;

const resizeAllCharts = () => {
  requestPieChartRef.value?.chart?.resize();
  tokenPieChartRef.value?.chart?.resize();
  inputOutputBarChartRef.value?.chart?.resize();
  latencyComparisonChartRef.value?.chart?.resize();
};

const scheduleResizeAllCharts = () => {
  if (resizeRafId !== null) {
    cancelAnimationFrame(resizeRafId);
  }

  resizeRafId = window.requestAnimationFrame(() => {
    resizeRafId = null;
    resizeAllCharts();
  });
};

const formatChartValue = (value: number) =>
  new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);

const formatLatencyMsValue = (value: number) =>
  new Intl.NumberFormat("en-US", {
    minimumFractionDigits: value < 10 ? 2 : 1,
    maximumFractionDigits: 2,
  }).format(value);

const chartRows = (
  rows: Array<{ provider: string; value: number; color: string }>,
) => {
  const total = rows.reduce((sum, row) => sum + row.value, 0);

  return rows.map((row) => ({
    ...row,
    valueText: formatChartValue(row.value),
    percentText: total ? `${((row.value / total) * 100).toFixed(1)}%` : "--",
  }));
};

const pieOption = (
  rows: Array<{ provider: string; value: number; color: string }>,
  seriesName: string,
) => ({
  color:
    rows.reduce((sum, row) => sum + row.value, 0) > 0
      ? rows.map((row) => row.color)
      : ["#cbd5e1"],
  legend: { show: false },
  series: [
    {
      name: seriesName,
      type: "pie",
      radius: ["46%", "74%"],
      center: ["50%", "50%"],
      minAngle: 3,
      avoidLabelOverlap: true,
      silent: rows.reduce((sum, row) => sum + row.value, 0) === 0,
      label: {
        show: rows.reduce((sum, row) => sum + row.value, 0) > 0,
        formatter: "{d}%",
        color: "#475569",
        fontSize: 10,
      },
      labelLine: {
        show: rows.reduce((sum, row) => sum + row.value, 0) > 0,
        length: 10,
        length2: 8,
        lineStyle: { color: "#94a3b8" },
      },
      emphasis: {
        scale: true,
        scaleSize: 4,
      },
      data:
        rows.reduce((sum, row) => sum + row.value, 0) > 0
          ? rows.map((row) => ({ name: row.provider, value: row.value }))
          : [{ name: seriesName, value: 1, itemStyle: { color: "#cbd5e1" } }],
    },
  ],
});

const overallSeriesColor = "#64748b";

const providerChartPalette = [
  "#2f6fed",
  "#f59e0b",
  "#20a162",
  "#7c3aed",
  "#ef4444",
  "#06b6d4",
  "#84cc16",
  "#f97316",
];

const paletteColorAt = (index: number) =>
  providerChartPalette[index % providerChartPalette.length];

const requestLegendRows = computed(() =>
  chartRows(
    distributionProviderRows.value.map((row, index) => ({
      provider: row.provider,
      value: row.requestCount,
      color: paletteColorAt(index),
    })),
  ),
);

const tokenLegendRows = computed(() =>
  chartRows(
    tokenProviderRows.value.map((row, index) => ({
      provider: row.provider,
      value: row.totalTokens ?? 0,
      color: paletteColorAt(index),
    })),
  ),
);

const requestPieOption = computed(() =>
  pieOption(requestLegendRows.value, t("router.routerRequestShare")),
);
const tokenPieOption = computed(() =>
  pieOption(tokenLegendRows.value, t("router.routerTokenShare")),
);

const inputOutputSeriesRows = computed(() => [
  ...tokenProviderRows.value.map((row, index) => ({
    provider: row.provider,
    inputTokens: row.inputTokens ?? 0,
    outputTokens: row.outputTokens ?? 0,
    color: paletteColorAt(index),
  })),
  {
    provider: t("router.routerOverallLabel"),
    inputTokens: totalInputTokens.value,
    outputTokens: totalOutputTokens.value,
    color: overallSeriesColor,
  },
]);

const inputOutputBarOption = computed(() => ({
  grid: {
    top: 12,
    right: 12,
    bottom: 30,
    left: 50,
  },
  tooltip: {
    trigger: "axis",
    axisPointer: { type: "shadow" },
    formatter: (
      params: Array<{
        axisValue: string;
        marker: string;
        seriesName: string;
        value: number;
      }>,
    ) => {
      const lines = params
        .map(
          (item) =>
            `${item.marker}${item.seriesName}: ${formatChartValue(item.value)}`,
        )
        .join("<br/>");

      return `${params[0]?.axisValue ?? ""}<br/>${lines}`;
    },
  },
  xAxis: {
    type: "category",
    data: [
      t("router.routerTotalInputTokens"),
      t("router.routerTotalOutputTokens"),
    ],
    axisLine: {
      show: true,
      lineStyle: { color: "#94a3b8", width: 1 },
    },
    axisTick: {
      show: true,
      alignWithLabel: true,
      lineStyle: { color: "#94a3b8" },
    },
    axisLabel: {
      color: "#6b7280",
      fontSize: 10,
      interval: 0,
    },
  },
  yAxis: {
    type: "value",
    min: 0,
    axisLine: {
      show: true,
      lineStyle: { color: "#94a3b8", width: 1 },
    },
    axisTick: {
      show: true,
      lineStyle: { color: "#94a3b8" },
    },
    axisLabel: {
      show: true,
      color: "#6b7280",
      fontSize: 10,
      formatter: formatChartValue,
    },
    splitLine: {
      show: true,
      lineStyle: { color: "rgba(148, 163, 184, 0.24)" },
    },
  },
  series: [
    ...inputOutputSeriesRows.value.map((row) => ({
      name: row.provider,
      type: "bar",
      barMaxWidth: 18,
      barMinHeight: 2,
      data: [row.inputTokens, row.outputTokens],
      itemStyle: { color: row.color, borderRadius: [4, 4, 0, 0] },
      label: {
        show: false,
      },
    })),
  ],
}));

const routerRemainingRatio = computed(() =>
  Math.min(Math.max(routerCompressionRestPercentValue.value, 0), 100),
);
const routerCompressionPercent = computed(() =>
  Math.min(Math.max(routerCompressionPercentValue.value, 0), 100),
);

const clampPercent = (value: number) => Math.min(Math.max(value, 0), 100);
const systemPromptRemainingPercent = computed(() =>
  clampPercent(100 - systemPromptCompressionValue.value),
);
const systemPromptCompressionPercent = computed(() =>
  clampPercent(systemPromptCompressionValue.value),
);
const toolSchemaRemainingPercent = computed(() =>
  clampPercent(100 - toolSchemaCompressionValue.value),
);
const toolSchemaCompressionPercent = computed(() =>
  clampPercent(toolSchemaCompressionValue.value),
);
const contextRemainingPercent = computed(() =>
  clampPercent(100 - contextCompressionValue.value),
);
const contextCompressionPercent = computed(() =>
  clampPercent(contextCompressionValue.value),
);

const latencyProviderSeriesRows = computed(() => [
  ...latencyProviderRows.value.map((row, index) => ({
    provider: row.provider,
    avgLatencyMs: row.avgLatencyMs ?? 0,
    avgTtftMs: row.avgTtftMs ?? 0,
    avgTpotMs: row.avgTpotMs ?? 0,
    color: paletteColorAt(index),
  })),
  {
    provider: t("router.routerOverallLabel"),
    avgLatencyMs: avgLatencyMs.value ?? 0,
    avgTtftMs: avgTtftMs.value ?? 0,
    avgTpotMs: avgTpotMs.value ?? 0,
    color: overallSeriesColor,
  },
]);

const latencyComparisonOption = computed(() => {
  const rows = latencyProviderSeriesRows.value;
  const categories = [
    t("router.routerAvgLatencyMs"),
    t("router.routerAvgTtftMs"),
    t("router.routerAvgTpotMs"),
  ];

  return {
    grid: {
      top: 14,
      right: 14,
      bottom: 54,
      left: 50,
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (
        params: Array<{
          axisValue: string;
          marker: string;
          seriesName: string;
          value: number;
        }>,
      ) => {
        const lines = params
          .map(
            (item) =>
              `${item.marker}${item.seriesName}: ${formatLatencyMsValue(item.value)} ms`,
          )
          .join("<br/>");

        return `${params[0]?.axisValue ?? ""}<br/>${lines}`;
      },
    },
    legend: {
      type: "scroll",
      bottom: 0,
      left: "center",
      right: 4,
      itemWidth: 8,
      itemHeight: 8,
      itemGap: 8,
      pageIconColor: "#64748b",
      pageTextStyle: { color: "#64748b", fontSize: 8 },
      textStyle: { color: "#4b5563", fontSize: 8 },
      data: rows.map((row) => row.provider),
    },
    xAxis: {
      type: "category",
      data: categories,
      axisLine: {
        show: true,
        lineStyle: { color: "#94a3b8", width: 1 },
      },
      axisTick: {
        show: true,
        alignWithLabel: true,
        lineStyle: { color: "#94a3b8" },
      },
      axisLabel: {
        color: "#6b7280",
        fontSize: 10,
        interval: 0,
      },
    },
    yAxis: {
      type: "value",
      min: 0,
      splitNumber: 3,
      axisLine: {
        show: true,
        lineStyle: { color: "#94a3b8", width: 1 },
      },
      axisTick: {
        show: true,
        lineStyle: { color: "#94a3b8" },
      },
      axisLabel: {
        color: "#6b7280",
        fontSize: 9,
        formatter: (value: number) => `${formatLatencyMsValue(value)} ms`,
      },
      splitLine: {
        show: true,
        lineStyle: { color: "rgba(148, 163, 184, 0.22)" },
      },
    },
    series: [
      ...rows.map((row) => ({
        name: row.provider,
        type: "bar",
        barMaxWidth: 18,
        barMinHeight: 2,
        data: [row.avgLatencyMs, row.avgTtftMs, row.avgTpotMs],
        itemStyle: { color: row.color, borderRadius: [4, 4, 0, 0] },
        label: {
          show: false,
        },
      })),
    ],
  };
});

const METRICS_POLL_INTERVAL_MS = 5000;
let metricsPollingTimer: number | null = null;
let metricsRequest: Promise<void> | null = null;
let isUnmounted = false;

const fetchRouterMetricsData = () => {
  if (metricsRequest) return metricsRequest;

  metricsRequest = getRouterMetrics()
    .then((metrics) => {
      if (!isUnmounted) {
        metricsPayload.value = metrics;
      }
    })
    .finally(() => {
      metricsRequest = null;
    });
  return metricsRequest;
};

const scheduleNextMetricsPoll = () => {
  if (isUnmounted) return;
  metricsPollingTimer = window.setTimeout(() => {
    metricsPollingTimer = null;
    void runMetricsPoll().catch(() => undefined);
  }, METRICS_POLL_INTERVAL_MS);
};

const runMetricsPoll = async () => {
  try {
    await fetchRouterMetricsData();
  } finally {
    scheduleNextMetricsPoll();
  }
};

const handleRefreshMetrics = async () => {
  if (isMetricsRefreshing.value) return;
  isMetricsRefreshing.value = true;
  try {
    await fetchRouterMetricsData();
  } finally {
    isMetricsRefreshing.value = false;
  }
};

const handleResetMetrics = () => {
  if (isResetting.value) return;
  Modal.confirm({
    zIndex: 1500,
    mask: true,
    title: t("common.reset"),
    icon: createVNode(ExclamationCircleFilled, { class: "warring-icon" }),
    content: t("router.resetStats"),
    okText: t("common.reset"),
    cancelText: t("common.cancel"),
    async onOk() {
      if (isResetting.value) return;
      isResetting.value = true;
      try {
        if (metricsRequest) await metricsRequest;
        await resetRouterMetrics();
        await fetchRouterMetricsData();
      } finally {
        isResetting.value = false;
      }
    },
  });
};

watch(
  [
    () => requestLegendRows.value.length,
    () => tokenLegendRows.value.length,
    () => inputOutputSeriesRows.value.length,
    () => latencyProviderSeriesRows.value.length,
  ],
  async () => {
    await nextTick();
    scheduleResizeAllCharts();
  },
);

onMounted(async () => {
  isUnmounted = false;
  void runMetricsPoll().catch(() => undefined);
  await nextTick();
  scheduleResizeAllCharts();
  window.addEventListener("resize", scheduleResizeAllCharts);

  if (typeof ResizeObserver !== "undefined" && overviewRootRef.value) {
    resizeObserver = new ResizeObserver(() => {
      scheduleResizeAllCharts();
    });
    resizeObserver.observe(overviewRootRef.value);
  }
});

onUnmounted(() => {
  isUnmounted = true;
  if (metricsPollingTimer !== null) {
    window.clearTimeout(metricsPollingTimer);
    metricsPollingTimer = null;
  }
  window.removeEventListener("resize", scheduleResizeAllCharts);
  resizeObserver?.disconnect();
  resizeObserver = null;

  if (resizeRafId !== null) {
    cancelAnimationFrame(resizeRafId);
    resizeRafId = null;
  }
});
</script>

<style scoped lang="less">
.router-detail-module {
  min-width: 0;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0;
}

.router-overview-module {
  min-height: clamp(760px, 78vh, 960px);
  overflow-x: hidden;
  overflow-y: auto;
  padding-right: 4px;
}

.overview-card-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.router-overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-template-rows: repeat(2, minmax(0, 1fr));
  flex: 1;
  min-height: 0;
  column-gap: 12px;
  row-gap: 12px;
  min-width: 0;
}

.router-overview-card {
  --overview-accent: var(--color-primary);
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 14px;
  min-width: 0;
  min-height: 0;
  height: 100%;
  min-height: 320px;
  padding: 14px;
  border: 1px solid
    color-mix(in srgb, var(--border-main-color) 86%, transparent);
  border-radius: 8px;
  background: color-mix(
    in srgb,
    var(--surface-card-bg) 86%,
    var(--surface-panel-bg-strong) 14%
  );
}

.token-overview-card {
  --overview-accent: var(--color-warning);
}

.compression-overview-card {
  --overview-accent: var(--color-success);
}

.latency-overview-card {
  --overview-accent: var(--color-info, var(--color-primary));
}

.overview-card-heading {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: 10px;
  min-width: 0;
}

.overview-card-icon {
  flex: 0 0 32px;
  width: 32px;
  height: 32px;
  border: 1px solid color-mix(in srgb, var(--overview-accent) 28%, transparent);
  border-radius: 8px;
  background: color-mix(
    in srgb,
    var(--overview-accent) 12%,
    var(--surface-panel-bg-strong)
  );
  color: var(--overview-accent);
  font-size: 16px;
}

.overview-card-icon-group {
  display: inline-flex;
  align-items: flex-end;
  min-width: 42px;
}

.overview-card-icon-group .overview-card-icon + .overview-card-icon {
  width: 24px;
  height: 24px;
  margin-bottom: -2px;
  margin-left: -10px;
  border-radius: 7px;
  font-size: 13px;
}

.token-icon {
  --overview-accent: var(--color-primary);
}

.token-bar-icon {
  --overview-accent: var(--color-warning);
}

.compression-icon {
  --overview-accent: var(--color-success);
}

.latency-icon {
  --overview-accent: var(--color-purple);
}

.latency-caption-highlight {
  color: var(--color-success);
}

.overview-card-copy {
  min-width: 0;
}

.overview-card-copy h3,
.overview-card-copy p {
  margin: 0;
}

.overview-card-copy h3 {
  color: var(--font-main-color);
  font-size: var(--font-size-13);
  font-weight: 600;
  line-height: 1.25;
}

.overview-card-copy p {
  margin-top: 3px;
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
  line-height: 1.4;
}

.overview-card-total,
.compression-saved-stat {
  display: grid;
  justify-items: end;
  gap: 1px;
  min-width: 0;
  text-align: right;
}

.overview-card-total span,
.compression-saved-stat span {
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
}

.overview-card-total strong {
  color: var(--overview-accent);
  font-size: var(--font-size-15);
  font-weight: 800;
}

.request-card-content {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.8fr);
  align-items: center;
  gap: 12px;
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: auto;
}

.overview-pie-chart {
  width: 100%;
  min-width: 0;
  height: clamp(132px, 20vw, 176px);
}

.overview-provider-legend {
  display: grid;
  align-content: center;
  gap: 4px;
  min-width: 0;
  max-height: 134px;
  overflow-y: auto;
}

.overview-provider-row {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 5px;
  min-width: 0;
  padding-bottom: 4px;
  border-bottom: 1px solid
    color-mix(in srgb, var(--border-main-color) 68%, transparent);
  color: var(--font-text-color);
  font-size: var(--font-size-11);
}

.overview-provider-row:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.router-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.overview-provider-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.overview-provider-value {
  display: inline-flex;
  align-items: center;
  justify-content: end;
}
.overview-provider-row strong {
  color: var(--font-main-color);
  font-weight: 800;
}

.overview-provider-row small {
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
}

.overview-empty-state {
  display: grid;
  min-height: clamp(132px, 20vw, 176px);
  place-items: center;
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
  text-align: center;
}

.overview-empty-state.compact {
  min-height: clamp(104px, 15vw, 128px);
}

.overview-nodata-center {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  min-height: clamp(132px, 20vw, 176px);
}

.overview-nodata-center.compact {
  min-height: clamp(104px, 15vw, 128px);
}

.token-card-content {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.token-share-pane,
.token-input-output-pane {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  align-items: center;
  min-width: 0;
  min-height: 0;
  padding: 10px;
  border: 1px solid
    color-mix(in srgb, var(--border-main-color) 72%, transparent);
  border-radius: 7px;
  background: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 84%,
    transparent
  );
}

.token-share-pane {
  grid-template-columns: minmax(72px, 1.3fr) minmax(126px, 0.7fr);
  grid-template-rows: auto minmax(0, 1fr);
  column-gap: 8px;
}

.token-share-pane .overview-chart-heading {
  grid-column: 1 / -1;
}

.token-share-pane .token-share-nodata {
  grid-column: 1 / -1;
  grid-row: 2;
  align-self: stretch;
  justify-self: stretch;
}

.overview-chart-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  color: var(--font-main-color);
  font-size: var(--font-size-11);
  font-weight: 600;
}

.overview-chart-heading small {
  flex: 0 0 auto;
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
  font-weight: 600;
}

.token-pie-chart {
  width: 100%;
  height: clamp(96px, 12vw, 120px);
  justify-self: center;
}

.input-output-bar-chart {
  width: 100%;
  height: clamp(132px, 18vw, 170px);
  justify-self: center;
}

.provider-inline-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 4px;
  align-content: flex-start;
  max-height: 46px;
  overflow-y: auto;
  padding-top: 2px;
}

.provider-inline-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  max-width: 100%;
  padding: 1px 6px;
}

.provider-inline-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--font-tip-color);
  font-size: 9px;
}

.token-provider-legend {
  grid-column: 2;
  grid-row: 2;
  width: 100%;
  max-height: 160px;
  align-self: center;
  align-content: start;
  gap: 3px;
}

.token-provider-legend .overview-provider-row {
  grid-template-columns: 8px minmax(0, 1fr) auto;
  gap: 4px;
  padding-bottom: 3px;
  font-size: 9px;
}

.token-provider-legend .overview-provider-row small {
  grid-column: 2 / -1;
  font-size: 9px;
  line-height: 1.1;
}

.compression-saved-stat strong {
  color: var(--color-success);
  font-size: var(--font-size-15);
  font-weight: 800;
}

.restored-compression-content {
  display: grid;
  grid-template-rows: minmax(0, 1fr) 80px;
  gap: 10px;
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  padding-right: 2px;
}

.router-consumption-summary {
  display: grid;
  min-height: 0;
  min-width: 0;
}

.router-summary-main {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  align-content: start;
  gap: 8px;
  min-width: 0;
  min-height: 0;
  height: 100%;
  padding: 10px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 18%, transparent);
  border-radius: 10px;
  background: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 82%,
    var(--color-primarySoft) 18%
  );
}
.router-summary-wrap {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas:
    "spacer copy"
    "track track";
  align-items: start;
  gap: 6px;
}
.router-summary-copy {
  grid-area: copy;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  min-width: 0;
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
  text-align: right;
}

.router-summary-title {
  grid-area: spacer;
  align-self: center;
  color: var(--font-main-color);
  font-size: var(--font-size-13);
  font-weight: 700;
}

.router-summary-copy-label {
  color: var(--font-tip-color);
}

.router-summary-copy-value {
  color: var(--font-main-color);
  font-size: var(--font-size-12);
  font-weight: 600;
}

.router-stack-track {
  grid-area: track;
  display: flex;
  height: 12px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--color-primary) 20%, transparent);
  border-radius: 999px;
  background: color-mix(
    in srgb,
    var(--surface-card-bg) 82%,
    var(--surface-panel-bg-strong) 18%
  );
}

.router-segment-tooltip {
  display: block;
  height: 100%;
}

.router-stack-segment {
  display: block;
  width: 100%;
  height: 100%;
}

.router-consumed {
  border-radius: 999px 0 0 999px;
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--color-primary) 88%, var(--font-main-color) 12%),
    color-mix(in srgb, var(--color-primary) 62%, var(--color-primarySoft) 38%)
  );
}

.router-saved {
  border-radius: 0 999px 999px 0;
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--color-warning) 84%, var(--color-white) 16%),
    color-mix(in srgb, var(--color-warning) 58%, var(--color-warningSoft) 42%)
  );
}

.router-summary-breakdown {
  display: grid;
  grid-template-columns: 1fr;
  grid-auto-rows: minmax(0, 1fr);
  gap: 6px;
  min-height: 0;
}

.router-breakdown-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: 0;
  height: 100%;
  padding: 12px 8px;
  border: 1px solid transparent;
  border-radius: 7px;
  font-size: var(--font-size-12);
  font-weight: 600;
}

.router-breakdown-main {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.router-consumption-row {
  color: var(--color-primary);
  background: color-mix(
    in srgb,
    var(--color-primarySoft) 42%,
    var(--surface-panel-bg-strong) 58%
  );
  border-color: color-mix(in srgb, var(--color-primary) 28%, transparent);
}

.router-saved-row {
  color: var(--color-warning);
  background: color-mix(
    in srgb,
    var(--color-warningSoft) 42%,
    var(--surface-panel-bg-strong) 58%
  );
  border-color: color-mix(in srgb, var(--color-warning) 28%, transparent);
}

.router-dot.consumed {
  background: var(--color-primary);
}

.router-dot.saved {
  background: var(--color-warning);
}

.router-breakdown-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  height: 80px;
  gap: 8px;
  min-width: 0;
  min-height: 0;
}

.router-breakdown-card {
  --router-card-accent: var(--color-primary);
  --router-card-soft: var(--color-primarySoft);
  --router-card-track: var(--surface-card-bg);
  display: grid;
  align-content: start;
  gap: 7px;
  min-width: 0;
  padding: 8px;
  border: 1px solid
    color-mix(in srgb, var(--router-card-accent) 20%, transparent);
  border-radius: 8px;
  background: linear-gradient(
    145deg,
    color-mix(
      in srgb,
      var(--router-card-soft) 36%,
      var(--surface-panel-bg-strong) 64%
    ),
    color-mix(
      in srgb,
      var(--router-card-track) 76%,
      var(--surface-panel-bg-strong) 24%
    )
  );
}

.router-breakdown-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 6px;
  min-width: 0;
}

.router-breakdown-card-label {
  min-width: 0;
  color: var(--font-main-color);
  font-size: var(--font-size-11);
  font-weight: 600;
}

.router-breakdown-card .router-summary-copy {
  flex: 0 0 auto;
  font-size: 9px;
}

.router-breakdown-card .router-summary-copy-value {
  font-size: var(--font-size-11);
}

.router-breakdown-bar-track {
  display: flex;
  height: 8px;
  overflow: hidden;
  border: 1px solid
    color-mix(in srgb, var(--router-card-accent) 18%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--router-card-track) 88%, transparent);
}

.router-breakdown-bar {
  display: block;
  width: 100%;
  height: 100%;
}

.router-breakdown-bar.consumed {
  border-radius: 999px 0 0 999px;
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--color-primary) 86%, var(--font-main-color) 14%),
    color-mix(in srgb, var(--color-primary) 58%, var(--color-primarySoft) 42%)
  );
}

.router-breakdown-bar.saved {
  border-radius: 0 999px 999px 0;
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--color-warning) 82%, var(--color-white) 18%),
    color-mix(in srgb, var(--color-warning) 56%, var(--color-warningSoft) 44%)
  );
}

.router-breakdown-card-metrics {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.router-breakdown-metric {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  min-width: 0;
}

.router-breakdown-metric .saved-label {
  min-width: 0;
  overflow: hidden;
  color: var(--font-tip-color);
  font-size: 9px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.router-breakdown-metric .saved-value {
  flex: 0 0 auto;
  color: var(--font-main-color);
  font-size: 9px;
  font-weight: 600;
}

.saved-value-percent {
  color: var(--color-warning);
}

.router-breakdown-card.tone-system {
  --router-card-accent: var(--color-warning);
  --router-card-soft: color-mix(
    in srgb,
    var(--color-warningSoft) 82%,
    var(--color-white) 18%
  );
  --router-card-track: color-mix(
    in srgb,
    var(--surface-card-bg) 74%,
    var(--color-warningSoft) 26%
  );
}

.router-breakdown-card.tone-tool {
  --router-card-accent: var(--color-info, var(--color-primary));
  --router-card-soft: color-mix(
    in srgb,
    var(--color-infoBg, var(--color-primarySoft)) 82%,
    var(--color-white) 18%
  );
  --router-card-track: color-mix(
    in srgb,
    var(--surface-card-bg) 76%,
    var(--color-infoBg, var(--color-primarySoft)) 24%
  );
}

.router-breakdown-card.tone-context {
  --router-card-accent: var(--color-success);
  --router-card-soft: color-mix(
    in srgb,
    var(--color-successSoft) 82%,
    var(--color-white) 18%
  );
  --router-card-track: color-mix(
    in srgb,
    var(--surface-card-bg) 76%,
    var(--color-successSoft) 24%
  );
}

.latency-preference {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  color: var(--color-success);
  font-size: var(--font-size-11);
  font-weight: 600;
  white-space: nowrap;
}

.latency-card-content {
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.latency-comparison-chart {
  width: 100%;
  height: 100%;
  min-height: clamp(146px, 20vw, 188px);
}

@media (max-width: 760px) {
  .router-overview-module {
    min-height: 0;
    overflow: visible;
    padding-right: 0;
  }

  .router-detail-module {
    display: block;
    height: auto;
    overflow: visible;
  }

  .router-overview-grid {
    grid-template-columns: 1fr;
    grid-template-rows: none;
    gap: 10px;
  }

  .router-overview-card {
    height: auto;
    min-height: 0;
    padding: 12px;
    overflow: visible;
  }

  .request-card-content,
  .token-card-content,
  .latency-card-content,
  .restored-compression-content {
    grid-template-columns: 1fr;
    height: auto;
    overflow: visible;
  }

  .request-card-content {
    gap: 8px;
  }

  .overview-provider-legend {
    max-height: none;
  }

  .token-card-content {
    gap: 8px;
  }

  .token-pie-chart {
    height: clamp(124px, 34vw, 142px);
  }

  .input-output-bar-chart {
    height: clamp(140px, 42vw, 188px);
  }

  .latency-comparison-chart {
    min-height: clamp(150px, 44vw, 204px);
  }

  .token-provider-legend {
    grid-column: auto;
    grid-row: auto;
    max-height: 96px;
  }

  .token-share-pane {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(0, 1fr) auto;
  }

  .token-share-pane .overview-chart-heading {
    grid-column: auto;
  }

  .router-summary-main {
    grid-template-rows: auto minmax(0, 1fr);
  }

  .router-summary-wrap {
    grid-template-columns: 1fr;
    grid-template-areas:
      "copy"
      "track";
  }

  .router-summary-breakdown {
    grid-template-columns: 1fr;
  }

  .router-breakdown-grid {
    grid-template-columns: 1fr;
    height: auto;
  }
}
</style>
