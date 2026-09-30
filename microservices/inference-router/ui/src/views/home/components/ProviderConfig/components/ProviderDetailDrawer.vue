<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <a-drawer
    :open="true"
    :title="t('router.routerProviderDetailTitle')"
    placement="right"
    :width="520"
    class="router-provider-detail-drawer"
    @close="emit('close')"
  >
    <div class="router-provider-detail-content">
      <section class="router-provider-detail-section">
        <div class="router-provider-detail-heading">
          {{ t("router.routerProviderBasicInfo") }}
        </div>
        <ul class="provider-detail-list">
          <li>
            <span>{{ t("router.routerProviderName") }}</span>
            <strong>{{ provider.name }}</strong>
          </li>
          <li>
            <span>{{ t("router.routerProviderType") }}</span>
            <strong>{{ provider.type }}</strong>
          </li>
          <li>
            <span>{{ t("router.routerProviderModel") }}</span>
            <strong>{{ provider.model }}</strong>
          </li>
          <li>
            <span>{{ t("router.routerProviderEnabled") }}</span>
            <strong>{{ provider.enabled }}</strong>
          </li>
        </ul>
      </section>
      <section class="router-provider-detail-section">
        <div class="router-provider-detail-heading">
          {{ t("router.routerProviderMetadata") }}
        </div>
        <pre>{{ formatJsonBlock(provider.metadata) }}</pre>
      </section>
      <section class="router-provider-detail-section">
        <div class="router-provider-detail-heading">
          {{ t("router.routerProviderSettings") }}
        </div>
        <pre>{{ formatJsonBlock(provider.settings) }}</pre>
      </section>
    </div>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { formatJsonText } from "@/utils/common";
import type { ConfigProviderRow } from "@/views/home/type";

const props = withDefaults(
  defineProps<{
    drawerData?: ConfigProviderRow;
  }>(),
  {
    drawerData: () => ({}),
  },
);

const emit = defineEmits<{ close: [] }>();
const { t } = useI18n();
const provider = computed(() => props.drawerData || {});

const formatJsonBlock = (value: unknown) => {
  return formatJsonText(value, {
    fallback: "--",
    emptyCollectionsAsFallback: false,
    emptyJsonStringsAsFallback: false,
  });
};
</script>

<style scoped lang="less">
.router-provider-detail-content {
  display: grid;
  gap: 14px;
}
.router-provider-detail-section {
  display: grid;
  gap: 10px;
}
.router-provider-detail-heading {
  color: var(--font-main-color);
  font-size: var(--font-size-13);
  font-weight: 600;
}
.provider-detail-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.provider-detail-list li {
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
.provider-detail-list span {
  color: var(--font-tip-color);
  font-size: var(--font-size-12);
}
.provider-detail-list strong {
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
