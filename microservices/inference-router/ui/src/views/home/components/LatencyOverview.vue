<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <section class="router-detail-module router-latency-module" role="tabpanel">
    <div class="router-module-heading">
      <span class="section-icon"><ClockCircleOutlined /></span>
      <div>
        <div class="section-title">
          {{ t("router.routerLatencyOverallTitle") }}
        </div>
        <div class="section-caption">
          {{ t("router.routerLatencyOverallCaption") }}
        </div>
      </div>
      <div class="router-module-actions">
        <a-button
          type="text"
          shape="circle"
          size="small"
          :title="t('router.refresh')"
          :loading="isRefreshing"
          @click="$emit('refresh')"
        >
          <template #icon><ReloadOutlined /></template>
        </a-button>
      </div>
    </div>
    <div class="router-metrics-stack">
      <section class="router-metrics-card">
        <div class="router-metrics-card-title">
          {{ t("router.overallTotals") }}
        </div>
        <ul class="form-wrap latency-overview-list overall-inline-list">
          <li
            v-for="metric in overallMetrics"
            :key="metric.label"
            class="item-wrap overall-core-item"
            :class="metric.tone"
          >
            <div class="overall-item-main">
              <span class="overall-item-icon">
                <component :is="metric.icon" class="overall-core-icon" />
              </span>
              <div class="overall-item-copy">
                <span class="label-wrap">{{ metric.label }}</span>
                <span class="content-wrap">{{ metric.value }}</span>
              </div>
            </div>
          </li>
        </ul>
      </section>
      <section class="router-metrics-card">
        <div class="router-metrics-card-title">
          {{ t("router.routerProviderComparisonTitle") }}
        </div>
        <div v-if="drawerData.providerRows.length" class="provider-equal-grid">
          <article
            v-for="providerMetric in drawerData.providerRows"
            :key="`latency-${providerMetric.provider}`"
            class="provider-equal-card"
          >
            <div class="provider-card-header">
              <strong>{{ providerMetric.provider }}</strong>
              <span
                class="latency-pill"
                :class="
                  drawerData.latencyToneClass(providerMetric.avgLatencyMs)
                "
              >
                {{
                  drawerData.formatLatencyNullable(providerMetric.avgLatencyMs)
                }}
              </span>
            </div>
            <ul class="form-wrap provider-compact-list">
              <li class="item-wrap">
                <span class="label-wrap">{{
                  t("router.routerAvgTtftMs")
                }}</span>
                <span class="content-wrap">{{
                  drawerData.formatLatencyNullable(providerMetric.avgTtftMs)
                }}</span>
              </li>
              <li class="item-wrap">
                <span class="label-wrap">{{
                  t("router.routerAvgTpotMs")
                }}</span>
                <span class="content-wrap">{{
                  drawerData.formatLatencyNullable(providerMetric.avgTpotMs)
                }}</span>
              </li>
              <li class="item-wrap">
                <span class="label-wrap">{{
                  t("router.routerTtftCount")
                }}</span>
                <span class="content-wrap">{{
                  drawerData.formatCompactNullable(providerMetric.ttftCount)
                }}</span>
              </li>
              <li class="item-wrap">
                <span class="label-wrap">{{
                  t("router.routerTpotCount")
                }}</span>
                <span class="content-wrap">{{
                  drawerData.formatCompactNullable(providerMetric.tpotCount)
                }}</span>
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
import { computed } from "vue";
import type { PropType } from "vue";
import { useI18n } from "vue-i18n";
import {
  ClockCircleOutlined,
  ThunderboltOutlined,
  HistoryOutlined,
  ReloadOutlined,
} from "@ant-design/icons-vue";
import type { LatencyProviderRow } from "@/views/home/type";

interface RouterLatencyOverviewDrawerData {
  providerRows: LatencyProviderRow[];
  avgLatencyText: string;
  avgTtftText: string;
  avgTpotText: string;
  ttftCountText: string;
  tpotCountText: string;
  formatLatencyNullable: (value: number | null) => string;
  formatCompactNullable: (value: number | null) => string;
  latencyToneClass: (value: number | null) => string;
}

const props = defineProps({
  drawerData: {
    type: Object as PropType<RouterLatencyOverviewDrawerData>,
    required: true,
    default: () => ({
      providerRows: [],
      avgLatencyText: "--",
      avgTtftText: "--",
      avgTpotText: "--",
      ttftCountText: "--",
      tpotCountText: "--",
      formatLatencyNullable: () => "--",
      formatCompactNullable: () => "--",
      latencyToneClass: () => "empty",
    }),
  },
  isRefreshing: {
    type: Boolean,
    default: false,
  },
});

defineEmits<{
  refresh: [];
}>();

const drawerData = computed(() => props.drawerData);
const isRefreshing = computed(() => props.isRefreshing);

const { t } = useI18n();
const overallMetrics = computed(() => [
  {
    label: t("router.routerAvgLatencyMs"),
    value: drawerData.value.avgLatencyText,
    icon: ClockCircleOutlined,
    tone: "core-latency",
  },
  {
    label: t("router.routerAvgTtftMs"),
    value: drawerData.value.avgTtftText,
    icon: ThunderboltOutlined,
    tone: "core-ttft",
  },
  {
    label: t("router.routerAvgTpotMs"),
    value: drawerData.value.avgTpotText,
    icon: ThunderboltOutlined,
    tone: "core-tpot",
  },
  {
    label: t("router.routerTtftCount"),
    value: drawerData.value.ttftCountText,
    icon: HistoryOutlined,
    tone: "core-count",
  },
  {
    label: t("router.routerTpotCount"),
    value: drawerData.value.tpotCountText,
    icon: HistoryOutlined,
    tone: "core-count",
  },
]);
</script>

<style scoped lang="less">
.router-detail-module {
  min-width: 0;
  min-height: 100%;
  overflow: visible;
  padding: 0;
  background: transparent;
}
.router-module-heading {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid
    color-mix(in srgb, var(--border-main-color) 78%, transparent);
}
.section-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 28px;
  width: 28px;
  height: 28px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 22%, transparent);
  background: var(--color-primary);
  color: var(--color-white);
}
.section-title {
  font-size: var(--font-size-13);
  font-weight: 600;
}
.section-caption,
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

.overall-item-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.overall-item-icon {
  display: inline-flex;
  justify-content: center;
  width: 16px;
  flex: 0 0 16px;
}

.overall-item-copy {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.overall-core-item.core-latency {
  border-color: color-mix(in srgb, var(--color-primary) 30%, transparent);
  background: color-mix(
    in srgb,
    var(--color-primarySoft) 62%,
    var(--surface-panel-bg-strong) 38%
  );
}

.overall-core-item.core-ttft {
  border-color: color-mix(in srgb, var(--color-warning) 30%, transparent);
  background: color-mix(
    in srgb,
    var(--color-warningSoft) 62%,
    var(--surface-panel-bg-strong) 38%
  );
}

.overall-core-item.core-tpot {
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
.overall-core-item.core-count {
  border-color: color-mix(in srgb, var(--color-success) 30%, transparent);
  background: color-mix(
    in srgb,
    var(--color-successSoft) 62%,
    var(--surface-panel-bg-strong) 38%
  );
}

.overall-core-item.core-latency .content-wrap,
.overall-core-item.core-latency .overall-core-icon {
  color: var(--color-primary);
}

.overall-core-item.core-ttft .content-wrap,
.overall-core-item.core-ttft .overall-core-icon {
  color: var(--color-warning-strong);
}

.overall-core-item.core-tpot .content-wrap,
.overall-core-item.core-tpot .overall-core-icon {
  color: var(--color-purple, var(--color-primary));
}

.overall-core-item.core-count .content-wrap,
.overall-core-item.core-count .overall-core-icon {
  color: var(--color-success);
}
.label-wrap,
.content-wrap {
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
  text-align: right;
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
.provider-compact-list .item-wrap {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: auto;
  gap: 6px;
  padding: 12px 8px;
}
.latency-pill {
  flex: 0 0 auto;
  min-width: 74px;
  padding: 2px 7px;
  border-radius: 999px;
  text-align: center;
  font-size: var(--font-size-11);
}
.latency-pill.good {
  color: var(--color-success);
  background: color-mix(
    in srgb,
    var(--color-successSoft) 56%,
    var(--surface-panel-bg-strong) 44%
  );
}
.latency-pill.neutral {
  color: var(--color-warning-strong);
  background: color-mix(
    in srgb,
    var(--color-warningSoft) 56%,
    var(--surface-panel-bg-strong) 44%
  );
}
.latency-pill.bad {
  color: var(--color-error, var(--color-errorBg));
  background: color-mix(
    in srgb,
    var(--color-error, var(--color-errorBg)) 8%,
    var(--surface-panel-bg-strong)
  );
}
.latency-pill.empty {
  color: var(--font-tip-color);
  background: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 78%,
    transparent
  );
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
