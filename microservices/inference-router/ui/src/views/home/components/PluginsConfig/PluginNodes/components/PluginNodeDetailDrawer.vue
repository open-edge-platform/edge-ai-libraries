<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <a-drawer
    :open="true"
    :title="t('router.routerPluginNodeDetailTitle')"
    placement="right"
    :width="560"
    @close="emit('close')"
  >
    <div class="plugin-node-detail">
      <dl>
        <div>
          <dt>{{ t("router.routerPluginNode") }}</dt>
          <dd>{{ node.node }}</dd>
        </div>
        <div>
          <dt>{{ t("router.routerPluginGroup") }}</dt>
          <dd>{{ node.plugin_group || "--" }}</dd>
        </div>
      </dl>
      <section>
        <h4>{{ t("router.routerPluginDescription") }}</h4>
        <p>{{ node.description || "--" }}</p>
      </section>
      <section>
        <h4>{{ t("router.routerPluginSettingsSchema") }}</h4>
        <pre>{{ formatJsonBlock(node.settings_schema) }}</pre>
      </section>
      <section v-if="extraNodeData">
        <h4>{{ t("router.routerPluginNodeRuntimeInfo") }}</h4>
        <pre>{{ formatJsonBlock(extraNodeData) }}</pre>
      </section>
    </div>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { formatJsonText } from "@/utils/common";
import type { PluginNodeRow } from "@/views/home/type";

const props = defineProps<{ drawerData: PluginNodeRow }>();
const emit = defineEmits<{ close: [] }>();
const { t } = useI18n();
const node = computed(() => props.drawerData);
const extraNodeData = computed(() => {
  const {
    node: _node,
    plugin_group,
    description,
    settings_schema,
    ...extra
  } = props.drawerData;
  return Object.keys(extra).length ? extra : null;
});
const formatJsonBlock = (value: unknown) =>
  formatJsonText(value, {
    fallback: "--",
    emptyCollectionsAsFallback: false,
    emptyJsonStringsAsFallback: false,
  });
</script>

<style scoped lang="less">
.plugin-node-detail,
.plugin-node-detail section {
  display: grid;
  gap: 10px;
}
.plugin-node-detail {
  gap: 16px;
}
.plugin-node-detail dl {
  display: grid;
  gap: 8px;
  margin: 0;
}
.plugin-node-detail dl div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--border-main-color) 72%, transparent);
  border-radius: 8px;
  background: var(--surface-panel-bg-strong);
}
.plugin-node-detail dt {
  color: var(--font-tip-color);
  font-size: var(--font-size-12);
}
.plugin-node-detail dd {
  margin: 0;
  color: var(--font-main-color);
  font-size: var(--font-size-12);
  font-weight: 600;
}
.plugin-node-detail h4,
.plugin-node-detail p,
.plugin-node-detail pre {
  margin: 0;
}
.plugin-node-detail h4 {
  color: var(--font-main-color);
  font-size: var(--font-size-13);
}
.plugin-node-detail p {
  color: var(--font-text-color);
  font-size: var(--font-size-12);
  line-height: 1.65;
}
.plugin-node-detail pre {
  max-height: 360px;
  padding: 12px;
  overflow: auto;
  border: 1px solid color-mix(in srgb, var(--border-main-color) 72%, transparent);
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