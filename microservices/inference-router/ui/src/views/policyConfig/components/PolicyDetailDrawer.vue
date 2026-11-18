<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <a-drawer
    :open="true"
    :title="t('router.routerPolicyDetailTitle')"
    placement="right"
    :width="520"
    class="router-policy-detail-drawer"
    @close="emit('close')"
  >
    <div class="router-policy-detail-content">
      <section class="router-policy-detail-section">
        <div class="router-policy-detail-heading">
          {{ t("router.routerPolicyBasicInfo") }}
        </div>
        <ul class="policy-detail-list">
          <li>
            <span>{{ t("router.routerPolicyName") }}</span>
            <strong>{{ policy.name }}</strong>
          </li>
          <li>
            <span>{{ t("router.routerPolicyCriterion") }}</span>
            <strong>{{ policy.criterion }}</strong>
          </li>
          <li>
            <span>{{ t("router.routerPolicyStrategiesCount") }}</span>
            <strong>{{ strategies.length }}</strong>
          </li>
        </ul>
      </section>
      <section class="router-policy-detail-section">
        <div class="router-policy-detail-heading">
          <span>{{ t("router.routerPolicyAssociatedStrategies") }}</span>
          <span class="router-policy-detail-tip">
            <ExclamationCircleFilled class="router-tip-icon" />
            {{ t("router.routerPolicyAssociatedStrategiesTip") }}
          </span>
        </div>
        <div class="policy-detail-strategies">
          <button
            v-for="strategyName in strategies"
            :key="strategyName"
            type="button"
            class="policy-detail-strategy-tag"
            @click="emit('viewStrategy', strategyName)"
          >
            {{ strategyName }}
          </button>
          <span
            v-if="!strategies.length"
            class="policy-detail-strategy-tag is-empty"
          >
            {{ t("router.routerPolicyNoStrategies") }}
          </span>
        </div>
      </section>
    </div>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { ExclamationCircleFilled } from "@ant-design/icons-vue";
import type { PolicyConfigRow } from "@/types/router";

const props = withDefaults(
  defineProps<{
    drawerData?: PolicyConfigRow;
  }>(),
  {
    drawerData: () => ({ name: "", criterion: "FirstMatch", strategies: [] }),
  },
);

const emit = defineEmits<{
  close: [];
  viewStrategy: [strategyName: string];
}>();
const { t } = useI18n();
const policy = computed(() => props.drawerData);
const strategies = computed(() => policy.value.strategies);
</script>

<style scoped lang="less">
.router-policy-detail-content {
  display: grid;
  gap: 14px;
}
.router-policy-detail-section {
  display: grid;
  gap: 10px;
}
.router-policy-detail-heading {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--font-main-color);
  font-size: var(--font-size-13);
  font-weight: 600;
}
.router-policy-detail-tip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
  font-weight: 400;
}
.router-tip-icon {
  color: var(--color-warning-strong);
  font-size: var(--font-size-12);
}
.policy-detail-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.policy-detail-list li {
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
.policy-detail-list span {
  color: var(--font-tip-color);
  font-size: var(--font-size-12);
}
.policy-detail-list strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--font-main-color);
  font-size: var(--font-size-12);
}
.policy-detail-strategies {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
  padding: 12px;
  border: 1px solid
    color-mix(in srgb, var(--border-main-color) 72%, transparent);
  border-radius: 8px;
  background: var(--surface-panel-bg-strong);
}
.policy-detail-strategy-tag {
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  min-width: 0;
  max-width: 100%;
  height: 20px;
  padding: 0 6px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  cursor: pointer;
  font-family: inherit;
  border: 1px solid color-mix(in srgb, var(--color-primary) 22%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-primarySoft) 72%, transparent);
  color: var(--color-primary);
  font-size: var(--font-size-11);
  font-weight: 500;
  line-height: 18px;
}
.policy-detail-strategy-tag:not(:disabled):not(.is-empty):hover {
  cursor: pointer;
  border-color: var(--color-primary);
  background: var(--color-primary);
  color: var(--color-white);
}
.policy-detail-strategy-tag:disabled,
.policy-detail-strategy-tag.is-empty {
  cursor: default;
  border-color: color-mix(in srgb, var(--border-main-color) 72%, transparent);
  background: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 82%,
    transparent
  );
  color: var(--font-tip-color);
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
