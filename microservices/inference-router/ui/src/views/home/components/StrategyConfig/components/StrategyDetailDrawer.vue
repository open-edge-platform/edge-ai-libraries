<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <a-drawer
    :open="true"
    :title="t('router.routerStrategyDetailTitle')"
    placement="right"
    :width="560"
    class="router-strategy-detail-drawer"
    @close="emit('close')"
  >
    <div class="router-strategy-detail-content">
      <section class="router-strategy-detail-section">
        <div class="router-strategy-detail-heading">
          {{ t("router.routerStrategyBasicInfo") }}
        </div>
        <ul class="strategy-detail-list">
          <li>
            <span>{{ t("router.routerStrategyName") }}</span>
            <strong>{{ strategy.name }}</strong>
          </li>
          <li>
            <span>{{ t("router.routerStrategyDescription") }}</span>
            <strong>{{ strategy.description || "--" }}</strong>
          </li>
          <li>
            <span>{{ t("router.routerStrategyRequireHealthy") }}</span>
            <strong>
              {{
                formatBooleanText(
                  strategy.require_healthy,
                  t("common.yes"),
                  t("common.no"),
                )
              }}
            </strong>
          </li>
          <li>
            <span>{{ t("router.routerStrategyLimit") }}</span>
            <strong>{{ formatLimit(strategy.limit) }}</strong>
          </li>
        </ul>
      </section>
      <section class="router-strategy-detail-section">
        <div class="router-strategy-detail-heading">
          {{ t("router.routerStrategyProviderSelector") }}
        </div>
        <pre>{{ formatJsonBlock(strategy.provider_selector) }}</pre>
      </section>
      <section class="router-strategy-detail-section">
        <div class="router-strategy-detail-heading">
          {{ t("router.routerStrategyRules") }}
        </div>
        <pre>{{ formatJsonBlock(strategy.rules) }}</pre>
      </section>

      <section class="router-strategy-detail-section">
        <div class="router-strategy-detail-heading">
          {{ t("router.routerStrategySort") }}
        </div>
        <pre>{{ formatJsonBlock(strategy.sort) }}</pre>
      </section>
    </div>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { formatBooleanText, formatJsonText } from "@/utils/common";
import type { StrategyConfigRow } from "@/views/home/type";

const props = withDefaults(
  defineProps<{
    drawerData?: StrategyConfigRow;
  }>(),
  {
    drawerData: () => ({}),
  },
);

const emit = defineEmits<{ close: [] }>();
const { t } = useI18n();
const strategy = computed(() => props.drawerData || {});

const formatLimit = (value: unknown) => {
  return value === null || value === undefined || value === ""
    ? "--"
    : String(value);
};

const formatJsonBlock = (value: unknown) => {
  return formatJsonText(value, { fallback: "--" });
};
</script>

<style scoped lang="less">
.router-strategy-detail-content {
  display: grid;
  gap: 14px;
}
.router-strategy-detail-section {
  display: grid;
  gap: 10px;
}
.router-strategy-detail-heading {
  color: var(--font-main-color);
  font-size: var(--font-size-13);
  font-weight: 600;
}
.strategy-detail-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.strategy-detail-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid
    color-mix(in srgb, var(--border-main-color) 72%, transparent);
  border-radius: 8px;
  background: var(--surface-panel-bg-strong);
}
.strategy-detail-list span {
  color: var(--font-tip-color);
  font-size: var(--font-size-12);
}
.strategy-detail-list strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--font-main-color);
  font-size: var(--font-size-12);
}
pre {
  max-height: 320px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  border: 1px solid
    color-mix(in srgb, var(--border-main-color) 72%, transparent);
  border-radius: 8px;
  background: var(--surface-panel-bg-strong);
  color: var(--font-main-color);
  font-family: Consolas, "Liberation Mono", monospace;
  font-size: var(--font-size-12);
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
