<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-drawer
    v-model:open="drawerVisible"
    :title="drawerData.name"
    width="min(700px, 100vw)"
    @close="handleClose"
  >
    <div class="source-heading">
      <div class="source-icon"><DeploymentUnitOutlined /></div>
      <div>
        <StatusTag
          :value="drawerData.reconciled ? 'reconciled' : 'unreconciled'"
        />
        <a-tag :bordered="false">
          {{ $t(`console.${drawerData.type}Source`) }}
        </a-tag>
        <p>{{ drawerData.id }}</p>
      </div>
    </div>
    <a-descriptions bordered :column="1" size="small">
      <a-descriptions-item :label="$t('console.database')">
        {{ drawerData.database_id }}
      </a-descriptions-item>
      <a-descriptions-item :label="$t('console.collection')">
        {{ drawerData.collection_name }}
      </a-descriptions-item>
      <a-descriptions-item :label="$t('console.status')">
        <template v-if="drawerData.enabled">
          {{ $t("console.enabled") }}
        </template>
        <template v-else>{{ $t("console.DISABLED") }}</template>
      </a-descriptions-item>
    </a-descriptions>
    <a-alert
      v-if="drawerData.reconciliation_error"
      type="error"
      showIcon
      :message="drawerData.reconciliation_error"
      class="notice-wrap"
    />
    <a-tabs>
      <a-tab-pane key="bindings" :tab="$t('console.pools')">
        <a-alert
          v-if="drawerData.type === 'object'"
          type="info"
          showIcon
          :message="$t('console.contentHint')"
        />
        <template v-for="pool in poolList" :key="pool.id">
          <h4>{{ pool.name }}</h4>
          <SourceBinding
            :library-data="libraryData"
            :pool="pool"
            :binding="
              pool.source_statuses.find(
                (item) => item.source_id === drawerData.id,
              )!
            "
            @search="handleSearch"
          />
        </template>
        <a-empty v-if="drawerData.type !== 'object' && !poolList.length" />
      </a-tab-pane>
      <a-tab-pane key="configuration" :tab="$t('console.sourceConfiguration')">
        <a-alert
          type="info"
          showIcon
          :message="$t('console.sourcesHint')"
          class="notice-wrap"
        />
        <JsonPretty
          v-if="Object.keys(drawerData.operator_options || {}).length"
          :data="drawerData.operator_options"
          :theme="themeStore.theme === 'dark' ? 'dark' : 'light'"
        />
        <a-empty v-else />
      </a-tab-pane>
    </a-tabs>
  </a-drawer>
</template>
<script lang="ts" setup name="DetailDrawer">
import { computed, ref } from "vue";
import { DeploymentUnitOutlined } from "@ant-design/icons-vue";
import type { Library, Source } from "@/api/console/type";
import { themeAppStore } from "@/store/theme";
import JsonPretty from "vue-json-pretty";
import "vue-json-pretty/lib/styles.css";
import StatusTag from "../../../components/StatusTag.vue";
import SourceBinding from "./SourceBinding.vue";
const props = defineProps<{ drawerData: Source; libraryData: Library }>();
const emit = defineEmits<{ close: []; search: [] }>();
const handleClose = () => emit("close");
const handleSearch = () => emit("search");
const themeStore = themeAppStore();
const drawerVisible = ref(true);
const poolList = computed(() =>
  props.libraryData.asset_pools.filter((pool) =>
    pool.source_statuses.some(
      (status) => status.source_id === props.drawerData.id,
    ),
  ),
);
</script>
<style scoped lang="less">
.source-heading {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 4px 0 24px;
  p {
    margin-top: 8px;
    font-size: 12px;
    font-family: monospace;
    color: var(--font-info-color);
  }
}
.source-icon {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  background: var(--bg-card-color);
  border-radius: 8px;
  font-size: 24px;
  color: var(--color-primary-second);
}
.notice-wrap {
  margin: 20px 0;
}
h4 {
  margin: 20px 0 12px;
  color: var(--font-main-color);
  font-weight: 500;
}
</style>
