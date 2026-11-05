<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <section class="router-detail-module router-token-module" role="tabpanel">
    <div class="router-module-heading">
      <span class="section-icon"><DatabaseOutlined /></span>
      <div>
        <div class="section-title">
          {{ t("router.routerTokenOverallTitle") }}
        </div>
        <div class="section-caption">
          {{ t("router.routerTokenOverallCaption") }}
        </div>
      </div>
      <div class="router-module-actions">
        <a-button
          type="text"
          shape="circle"
          size="small"
          :title="t('router.refresh')"
          :loading="isRefreshing"
          @click="handleRefreshMetrics"
        >
          <template #icon><ReloadOutlined /></template>
        </a-button>
      </div>
    </div>
    <div class="router-metrics-stack">
      <section class="router-metrics-card overview-overall-card">
        <div class="router-metrics-card-title">
          {{ t("router.overallTotals") }}
        </div>
        <ul
          class="form-wrap token-overview-list overall-inline-list overview-inline-list"
        >
          <li class="item-wrap overall-core-item core-requests">
            <div class="overall-item-main">
              <span class="overall-item-icon">
                <ApiOutlined class="overall-core-icon" />
              </span>
              <div class="overall-item-copy">
                <span class="label-wrap">{{
                  t("router.routerRequestCount")
                }}</span>
                <span class="content-wrap">{{ totalRequestsMetricText }}</span>
              </div>
            </div>
          </li>
          <li class="item-wrap overall-core-item core-tokens">
            <div class="overall-item-main">
              <span class="overall-item-icon">
                <DatabaseOutlined class="overall-core-icon" />
              </span>
              <div class="overall-item-copy">
                <span class="label-wrap">{{ t("router.totalTokens") }}</span>
                <span class="content-wrap">{{ totalTokensText }}</span>
              </div>
            </div>
          </li>
          <li class="item-wrap overall-core-item core-input">
            <div class="overall-item-main">
              <span class="overall-item-icon">
                <CloudUploadOutlined class="overall-core-icon" />
              </span>
              <div class="overall-item-copy">
                <span class="label-wrap">{{
                  t("router.routerTotalInputTokens")
                }}</span>
                <span class="content-wrap">{{ totalInputTokensText }}</span>
              </div>
            </div>
          </li>
          <li class="item-wrap overall-core-item core-output">
            <div class="overall-item-main">
              <span class="overall-item-icon">
                <CloudDownloadOutlined class="overall-core-icon" />
              </span>
              <div class="overall-item-copy">
                <span class="label-wrap">{{
                  t("router.routerTotalOutputTokens")
                }}</span>
                <span class="content-wrap">{{ totalOutputTokensText }}</span>
              </div>
            </div>
          </li>
          <li class="item-wrap overall-core-item core-avg">
            <div class="overall-item-main">
              <span class="overall-item-icon">
                <ThunderboltOutlined class="overall-core-icon" />
              </span>
              <div class="overall-item-copy">
                <span class="label-wrap">{{
                  t("router.routerAvgTokensPerRequest")
                }}</span>
                <span class="content-wrap">{{ avgTokensPerRequestText }}</span>
              </div>
            </div>
          </li>
        </ul>
      </section>

      <section class="router-metrics-card">
        <div class="router-metrics-card-title">
          {{ t("router.routerProviderComparisonTitle") }}
        </div>
        <div v-if="providerRows.length" class="provider-equal-grid">
          <article
            v-for="providerMetric in providerRows"
            :key="`token-${providerMetric.provider}`"
            class="provider-equal-card token-provider-card"
          >
            <div class="provider-card-header">
              <strong>{{ providerMetric.provider }}</strong>
              <span class="provider-share-pill">{{
                providerMetric.tokenShareText
              }}</span>
            </div>
            <ul class="form-wrap provider-compact-list">
              <li class="item-wrap">
                <span class="label-wrap">{{
                  t("router.routerRequestCount")
                }}</span>
                <span class="content-wrap">{{
                  formatCompactNullableValue(providerMetric.requestCount)
                }}</span>
              </li>
              <li class="item-wrap">
                <span class="label-wrap">{{ t("router.totalTokens") }}</span>
                <span class="content-wrap">{{
                  formatCompactNullableValue(providerMetric.totalTokens)
                }}</span>
              </li>
              <li class="item-wrap">
                <span class="label-wrap">{{
                  t("router.routerTotalInputTokens")
                }}</span>
                <span class="content-wrap">{{
                  formatCompactNullableValue(providerMetric.inputTokens)
                }}</span>
              </li>
              <li class="item-wrap">
                <span class="label-wrap">{{
                  t("router.routerTotalOutputTokens")
                }}</span>
                <span class="content-wrap">{{
                  formatCompactNullableValue(providerMetric.outputTokens)
                }}</span>
              </li>
              <li class="item-wrap provider-share-row">
                <span class="label-wrap">{{
                  t("router.routerRequestShare")
                }}</span>
                <div class="provider-share-bar-wrap">
                  <div class="provider-share-bar">
                    <i
                      :style="{
                        width: `${normalizeNumber(providerMetric.requestShare) * 100}%`,
                        background: providerMetric.color,
                      }"
                    ></i>
                  </div>
                  <span class="content-wrap">{{
                    providerMetric.requestShareText
                  }}</span>
                </div>
              </li>
              <li class="item-wrap provider-share-row">
                <span class="label-wrap">{{
                  t("router.routerTokenShare")
                }}</span>
                <div class="provider-share-bar-wrap">
                  <div class="provider-share-bar">
                    <i
                      :style="{
                        width: `${normalizeNumber(providerMetric.tokenShare) * 100}%`,
                        background: providerMetric.color,
                      }"
                    ></i>
                  </div>
                  <span class="content-wrap">{{
                    providerMetric.tokenShareText
                  }}</span>
                </div>
              </li>
            </ul>
          </article>
        </div>
        <NoData v-else />
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  ApiOutlined,
  CloudUploadOutlined,
  CloudDownloadOutlined,
  DatabaseOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons-vue";
import { getRouterMetrics } from "@/api/tokenOverview";
import { normalizeNumber } from "@/utils/common";
import {
  buildTokenProviderRows,
  formatCompactNullable,
  formatMaybeCompact,
  normalizeTokenProviderMetrics,
  providerColor,
} from "@/utils/routerMetrics";
import type { RouterMetricsPayload } from "@/types/router";

const { t } = useI18n();
const metricsPayload = ref<RouterMetricsPayload>({});
const isRefreshing = ref(false);
let metricsRequest: Promise<void> | null = null;

const fetchRouterMetrics = () => {
  if (metricsRequest) return metricsRequest;

  metricsRequest = getRouterMetrics()
    .then((metrics) => {
      metricsPayload.value = metrics;
    })
    .finally(() => {
      metricsRequest = null;
    });
  return metricsRequest;
};

const handleRefreshMetrics = async () => {
  if (isRefreshing.value) return;
  isRefreshing.value = true;
  try {
    await fetchRouterMetrics();
  } finally {
    isRefreshing.value = false;
  }
};

const emptyValueText = computed(() => t("router.routerEmptyValue"));
const tokenMetrics = computed(() => metricsPayload.value.token_metrics ?? {});
const tokenOverall = computed(() => tokenMetrics.value.overall ?? {});
const tokenProviderMetrics = computed(() =>
  normalizeTokenProviderMetrics(tokenMetrics.value.by_provider),
);
const providerRows = computed(() => {
  const rows = [...tokenProviderMetrics.value].sort((left, right) => {
    const leftShare = left.requestShare ?? Number.NEGATIVE_INFINITY;
    const rightShare = right.requestShare ?? Number.NEGATIVE_INFINITY;
    if (leftShare !== rightShare) return rightShare - leftShare;
    return left.provider.localeCompare(right.provider);
  });
  return buildTokenProviderRows(
    rows,
    (_, index) => providerColor(index),
    emptyValueText.value,
  );
});
const totalTokenRequestCount = computed(() => {
  const overallRequests = normalizeNumber(tokenOverall.value.total_requests);
  if (overallRequests > 0) return overallRequests;
  return tokenProviderMetrics.value.reduce(
    (sum, providerMetric) => sum + normalizeNumber(providerMetric.requestCount),
    0,
  );
});
const totalTokensText = computed(() =>
  formatMaybeCompact(tokenOverall.value.total_tokens, emptyValueText.value),
);
const totalInputTokensText = computed(() =>
  formatMaybeCompact(
    tokenOverall.value.total_input_tokens,
    emptyValueText.value,
  ),
);
const totalOutputTokensText = computed(() =>
  formatMaybeCompact(
    tokenOverall.value.total_output_tokens,
    emptyValueText.value,
  ),
);
const totalRequestsMetricText = computed(() =>
  formatMaybeCompact(totalTokenRequestCount.value, emptyValueText.value),
);
const avgTokensPerRequestText = computed(() => {
  const value = tokenOverall.value.avg_tokens_per_request;
  return Number.isFinite(Number(value)) ? String(value) : emptyValueText.value;
});
const formatCompactNullableValue = (value: number | null) =>
  formatCompactNullable(value, emptyValueText.value);

onMounted(() => {
  void handleRefreshMetrics().catch(() => undefined);
});
</script>

<style scoped lang="less">
.router-metrics-card-title {
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
}
.router-metrics-stack,
.router-metrics-card,
.form-wrap {
  display: grid;
  gap: 8px;
}
.router-metrics-card {
  padding: 8px;
  border: 1px solid
    color-mix(in srgb, var(--border-main-color) 76%, transparent);
  border-radius: 12px;
  background: color-mix(
    in srgb,
    var(--surface-card-bg) 72%,
    var(--surface-panel-bg-strong) 28%
  );
}
.form-wrap {
  margin: 0;
  padding: 0;
  list-style: none;
}
.overall-inline-list {
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 6px;
}
.item-wrap {
  min-width: 0;
  height: 56px;
  padding: 8px 9px;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, currentColor 10%, transparent);
  background: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 78%,
    transparent
  );
}

.overall-core-item.core-tokens {
  color: var(--color-primary);
  background: color-mix(
    in srgb,
    var(--color-primarySoft) 62%,
    var(--surface-panel-bg-strong) 38%
  );
}

.overall-core-item.core-input {
  border-color: color-mix(in srgb, var(--color-warning) 30%, transparent);
  background: color-mix(
    in srgb,
    var(--color-warningSoft) 62%,
    var(--surface-panel-bg-strong) 38%
  );
}

.overall-core-item.core-output {
  border-color: color-mix(
    in srgb,
    var(--color-purple, var(--color-primary)) 30%,
    transparent
  );
  background: color-mix(
    in srgb,
    var(--color-purpleBg, var(--color-primarySoft)) 62%,
    var(--surface-panel-bg-strong) 38%
  );
}
.overall-core-item.core-avg {
  border-color: color-mix(in srgb, var(--color-error) 30%, transparent);
  background: color-mix(
    in srgb,
    var(--color-errorSoft) 62%,
    var(--surface-panel-bg-strong) 38%
  );
}

.overall-core-item.core-requests {
  border-color: color-mix(in srgb, var(--color-success) 30%, transparent);
  background: color-mix(
    in srgb,
    var(--color-successSoft) 62%,
    var(--surface-panel-bg-strong) 38%
  );
}

.overall-core-item.core-tokens .content-wrap,
.overall-core-item.core-tokens .overall-core-icon {
  color: var(--color-primary);
}

.overall-core-item.core-input .content-wrap,
.overall-core-item.core-input .overall-core-icon {
  color: var(--color-warning);
}

.overall-core-item.core-output .content-wrap,
.overall-core-item.core-output .overall-core-icon {
  color: var(--color-purple, var(--color-primary));
}

.overall-core-item.core-requests .content-wrap,
.overall-core-item.core-requests .overall-core-icon {
  color: var(--color-success);
}
.overall-core-item.core-avg .content-wrap,
.overall-core-item.core-avg .overall-core-icon {
  color: var(--color-error);
}

.overall-item-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  width: 100%;
}
.overall-item-icon {
  display: inline-flex;
  justify-content: center;
  width: 16px;
  flex: 0 0 16px;
  .overall-core-icon {
    font-size: 18px;
  }
}
.overall-item-copy {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.label-wrap,
.content-wrap {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.label-wrap {
  color: var(--font-text-color);
  font-size: var(--font-size-11);
  font-weight: 600;
}
.content-wrap {
  color: var(--font-main-color);
  font-size: var(--font-size-14);
  font-weight: 600;
  min-width: 60px;
}
.provider-equal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 8px;
}
.provider-equal-card {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 8px;
  border-radius: 10px;
  border: 1px solid
    color-mix(in srgb, var(--border-main-color) 78%, transparent);
  background: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 80%,
    transparent
  );
}
.provider-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.provider-card-header strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--font-main-color);
  font-size: var(--font-size-11);
}
.provider-share-pill {
  flex: 0 0 auto;
  padding: 3px 7px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-primary) 10%, transparent);
  color: var(--color-primary);
  font-size: var(--font-size-11);
  font-weight: 800;
}
.provider-compact-list {
  grid-template-columns: minmax(0, 1fr);
  gap: 6px;
}
.provider-compact-list .item-wrap {
  min-height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 6px 8px;
}
.provider-compact-list .label-wrap {
  flex: 1;
}
.provider-compact-list .content-wrap {
  min-width: 0;
  flex: 0 0 auto;
  text-align: right;
}
.provider-share-bar-wrap {
  display: grid;
  grid-template-columns: minmax(58px, 1fr) 48px;
  align-items: center;
  gap: 8px;
  flex: 0 1 58%;
  min-width: 0;
}
.provider-share-bar {
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--border-main-color) 54%, transparent);
}
.provider-share-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
}
.router-empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 72px;
  color: var(--font-tip-color);
}
@media (max-width: 760px) {
  .overall-inline-list {
    grid-template-columns: 1fr;
  }
}
</style>
