<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <div v-if="loading" class="router-loading-state">
    {{ t("common.loading") }}
  </div>
  <div class="plugin-node-card-list">
    <article
      v-for="pluginNode in nodeRows"
      :key="pluginNode.node"
      class="plugin-node-card"
    >
      <div class="plugin-node-card-header">
        <span class="plugin-node-card-icon"><ApartmentOutlined /></span>
        <div class="plugin-node-card-title">
          <strong>{{ pluginNode.node }}</strong>
          <span>{{
            pluginNode.plugin_group || t("router.routerPluginUngrouped")
          }}</span>
        </div>
      </div>
      <p class="plugin-node-description">
        {{ pluginNode.description || t("router.routerPluginNoDescription") }}
      </p>
      <div class="plugin-node-card-actions">
        <a-button type="primary" size="small" @click="handleView(pluginNode)">
          <template #icon><EyeOutlined /></template>
          {{ t("common.detail") }}
        </a-button>
        <a-button size="small" @click="handleReset(pluginNode)">
          <template #icon><UndoOutlined /></template>
          {{ t("common.reset") }}
        </a-button>
      </div>
    </article>
    <div v-if="!loading && !nodeRows.length" class="router-empty-state">
      {{ t("router.routerNoPluginNodes") }}
    </div>
  </div>

  <PluginNodeDetailDrawer
    v-if="detailDrawer.visible"
    :drawer-data="detailDrawer.data"
    @close="detailDrawer.visible = false"
  />
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { Modal } from "ant-design-vue";
import {
  ApartmentOutlined,
  EyeOutlined,
  UndoOutlined,
} from "@ant-design/icons-vue";
import {
  getRouterPluginNode,
  getRouterPluginNodes,
  resetRouterPluginNode,
} from "@/api/router";
import { PluginNodeDetailDrawer } from "./components";
import type { PluginNodeRow } from "@/views/home/type";

const { t } = useI18n();
const loading = ref(false);
const nodeRows = ref<PluginNodeRow[]>([]);
const detailDrawer = reactive({
  visible: false,
  data: {} as PluginNodeRow,
});

const normalizeList = (response: unknown) => {
  if (Array.isArray(response)) return response as PluginNodeRow[];
  const { data } = (response || {}) as { data?: unknown };
  return Array.isArray(data) ? (data as PluginNodeRow[]) : [];
};

const normalizeDetail = (response: unknown) => {
  const responseRecord = (response || {}) as Record<string, unknown>;
  const { data } = responseRecord;
  if (data && !Array.isArray(data) && typeof data === "object") {
    return data as PluginNodeRow;
  }
  return responseRecord as PluginNodeRow;
};

const queryNodeList = async () => {
  loading.value = true;
  try {
    nodeRows.value = normalizeList(await getRouterPluginNodes());
  } catch (error) {
    console.log(error);
  } finally {
    loading.value = false;
  }
};

const handleView = async (pluginNode: PluginNodeRow) => {
  try {
    detailDrawer.data = {
      ...pluginNode,
      ...normalizeDetail(await getRouterPluginNode(pluginNode.node)),
    };
    detailDrawer.visible = true;
  } catch (error) {
    console.log(error);
  }
};

const handleReset = (pluginNode: PluginNodeRow) => {
  Modal.confirm({
    title: t("common.prompt"),
    content: t("router.routerPluginNodeResetConfirmContent", {
      node: pluginNode.node,
    }),
    okText: t("common.reset"),
    cancelText: t("common.cancel"),
    async onOk() {
      await resetRouterPluginNode(pluginNode.node);
    },
  });
};

defineExpose({ refresh: queryNodeList });
onMounted(queryNodeList);
</script>

<style scoped lang="less">
.plugin-node-card-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 380px));
  justify-content: start;
  gap: 16px;
}
.plugin-node-card {
  display: grid;
  gap: 14px;
  min-height: 196px;
  padding: 16px;
  border: 1px solid
    color-mix(in srgb, var(--color-white) 6%, var(--border-main-color));
  border-radius: 18px;
  background: color-mix(
    in srgb,
    var(--surface-card-bg) 82%,
    var(--surface-panel-bg-strong) 18%
  );
  box-shadow: 0 18px 36px
    color-mix(in srgb, var(--bg-box-shadow) 72%, transparent);
}
.plugin-node-card-header {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  min-width: 0;
}
.plugin-node-card-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 38px;
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-warning-strong) 14%, transparent);
  color: var(--color-warning-strong);
  font-size: 18px;
}
.plugin-node-card-title {
  display: grid;
  gap: 4px;
  min-width: 0;
}
.plugin-node-card-title strong,
.plugin-node-card-title span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.plugin-node-card-title strong {
  color: var(--font-main-color);
  font-size: var(--font-size-14);
}
.plugin-node-card-title span {
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
}
.plugin-node-description {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  color: var(--font-text-color);
  font-size: var(--font-size-12);
  line-height: 1.55;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: 3;
}
.plugin-node-card-actions {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  justify-content: flex-end;
  gap: 8px;
  margin-top: auto;
}
@media (max-width: 720px) {
  .plugin-node-card-list {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
