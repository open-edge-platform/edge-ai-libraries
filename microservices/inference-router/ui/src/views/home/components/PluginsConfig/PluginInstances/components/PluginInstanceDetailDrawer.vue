<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <a-drawer
    :open="true"
    :title="t('router.routerPluginDetailTitle')"
    placement="right"
    :width="520"
    @close="emit('close')"
  >
    <div class="plugin-detail-content">
      <section class="plugin-detail-section">
        <div class="plugin-detail-heading">
          {{ t("router.routerPluginBasicInfo") }}
        </div>
        <ul class="plugin-detail-list">
          <li>
            <span>{{ t("router.routerPluginName") }}</span
            ><strong>{{ plugin.name }}</strong>
          </li>
          <li>
            <span>{{ t("router.routerPluginNode") }}</span
            ><strong>{{ plugin.node }}</strong>
          </li>
          <li>
            <span>{{ t("router.routerPluginTrigger") }}</span
            ><strong>{{ plugin.trigger }}</strong>
          </li>
          <li>
            <span>{{ t("router.routerPluginEnabled") }}</span
            ><strong>{{ plugin.enabled }}</strong>
          </li>
        </ul>
      </section>
      <section class="plugin-detail-section">
        <div class="plugin-detail-heading">
          {{ t("router.routerPluginSettings") }}
        </div>
        <pre>{{ formatJsonBlock(plugin.settings) }}</pre>
      </section>
      <section
        v-if="plugin.metrics !== undefined"
        class="plugin-detail-section"
      >
        <div class="plugin-detail-heading">
          {{ t("router.routerPluginMetrics") }}
        </div>
        <pre>{{ formatJsonBlock(plugin.metrics) }}</pre>
      </section>
    </div>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { formatJsonText } from "@/utils/common";
import type { ConfigPluginRow } from "@/views/home/type";

const props = defineProps<{ drawerData: ConfigPluginRow }>();
const emit = defineEmits<{ close: [] }>();
const { t } = useI18n();
const plugin = computed(() => props.drawerData);
const formatJsonBlock = (value: unknown) =>
  formatJsonText(value, {
    fallback: "--",
    emptyCollectionsAsFallback: false,
    emptyJsonStringsAsFallback: false,
  });
</script>

<style scoped lang="less">
.plugin-detail-content,
.plugin-detail-section {
  display: grid;
  gap: 12px;
}
.plugin-detail-heading {
  color: var(--font-main-color);
  font-size: var(--font-size-13);
  font-weight: 600;
}
.plugin-detail-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.plugin-detail-list li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid
    color-mix(in srgb, var(--border-main-color) 72%, transparent);
  border-radius: 8px;
  background: var(--surface-panel-bg-strong);
}
.plugin-detail-list span {
  color: var(--font-tip-color);
  font-size: var(--font-size-12);
}
.plugin-detail-list strong {
  min-width: 0;
  overflow: hidden;
  color: var(--font-main-color);
  font-size: var(--font-size-12);
  text-overflow: ellipsis;
  white-space: nowrap;
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
