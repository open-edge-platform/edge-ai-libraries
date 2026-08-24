<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <section class="router-detail-module router-config-module" role="tabpanel">
    <div class="router-module-heading">
      <span class="section-icon"><AppstoreOutlined /></span>
      <div>
        <div class="section-title">
          {{ t("router.routerPluginConfigTitle") }}
        </div>
        <div class="section-caption">
          {{ t("router.routerPluginConfigCaption") }}
        </div>
      </div>
      <div class="router-module-actions">
        <a-button
          type="text"
          shape="circle"
          size="small"
          :title="t('router.refresh')"
          :loading="isRefreshing"
          @click="handleRefresh"
        >
          <template #icon><ReloadOutlined /></template>
        </a-button>
      </div>
    </div>

    <a-tabs v-model:activeKey="activeResource" class="plugin-resource-tabs">
      <a-tab-pane key="instances" :tab="t('router.routerPluginInstancesTab')">
        <PluginInstances ref="instancesRef" />
      </a-tab-pane>
      <a-tab-pane key="nodes" :tab="t('router.routerPluginNodesTab')">
        <PluginNodes ref="nodesRef" />
      </a-tab-pane>
    </a-tabs>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { AppstoreOutlined, ReloadOutlined } from "@ant-design/icons-vue";
import { reloadRouterConfig } from "@/api/router";
import PluginInstances from "./PluginInstances/index.vue";
import PluginNodes from "./PluginNodes/index.vue";

interface RefreshableComponent {
  refresh: () => Promise<void>;
}

const { t } = useI18n();
const activeResource = ref("instances");
const isRefreshing = ref(false);
const instancesRef = ref<RefreshableComponent>();
const nodesRef = ref<RefreshableComponent>();

const refreshResources = () =>
  Promise.all([instancesRef.value?.refresh(), nodesRef.value?.refresh()]);

const handleRefresh = async () => {
  if (isRefreshing.value) return;
  isRefreshing.value = true;
  try {
    await refreshResources();
  } finally {
    isRefreshing.value = false;
  }
};
</script>

<style scoped lang="less">
.plugin-resource-tabs {
  min-height: 0;
}
.plugin-resource-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 16px;
}
.plugin-resource-tabs :deep(.ant-tabs-content-holder),
.plugin-resource-tabs :deep(.ant-tabs-content),
.plugin-resource-tabs :deep(.ant-tabs-tabpane) {
  min-width: 0;
}
</style>
