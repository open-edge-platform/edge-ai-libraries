<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div class="model-container">
    <div class="model-content" :aria-busy="loading">
      <a-card :bordered="false" class="model-card">
        <div class="header-wrap">
          <div class="title-wrap">
            <div class="model-icon"><CloudServerOutlined /></div>
            <div>
              <h3>{{ $t("console.modelRegistry") }}</h3>
              <p>{{ $t("console.modelsHint") }}</p>
            </div>
          </div>
          <a-button :loading="loading" @click="handleRefresh">
            <template #icon><ReloadOutlined /></template>
            {{ $t("console.refresh") }}
          </a-button>
        </div>
        <a-tabs
          v-if="Object.keys(modelData).length"
          v-model:activeKey="activeKey"
          class="model-tabs"
        >
          <a-tab-pane v-for="(item, key) in modelData" :key="String(key)">
            <template #tab>
              <span class="tab-title">
                <DeploymentUnitOutlined />
                {{ $te(`console.${key}`) ? $t(`console.${key}`) : key }}
                <a-tag :bordered="false">{{ item.models.length }}</a-tag>
              </span>
            </template>
            <ModelDetail :model-data="item" />
          </a-tab-pane>
        </a-tabs>
        <a-empty v-else />
      </a-card>
    </div>
  </div>
</template>
<script lang="ts" setup name="ConsoleModels">
import { onMounted, ref } from "vue";
import {
  CloudServerOutlined,
  DeploymentUnitOutlined,
  ReloadOutlined,
} from "@ant-design/icons-vue";
import { getModelList } from "@/api/console";
import type { ModelOptions } from "@/api/console/type";
import ModelDetail from "./components/ModelDetail.vue";
const loading = ref(false);
const activeKey = ref("");
const modelData = ref<Record<string, ModelOptions>>({});
const queryModelList = async () => {
  loading.value = true;
  try {
    modelData.value = await getModelList();
    if (!modelData.value[activeKey.value])
      activeKey.value = Object.keys(modelData.value)[0] || "";
  } finally {
    loading.value = false;
  }
};
const handleRefresh = () => queryModelList();
onMounted(queryModelList);
</script>
<style scoped lang="less">
.model-content,
.model-card {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.model-card :deep(> .intel-card-body) {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.model-card {
  background: var(--bg-content-color);
  border: 1px solid var(--border-main-color);
  border-radius: 8px;
  :deep(.intel-card-body) {
    padding: 0;
  }
}
.header-wrap {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  flex-shrink: 0;
  flex-wrap: wrap;
}
.title-wrap {
  display: flex;
  align-items: center;
  gap: 14px;
  h3 {
    margin: 0 0 6px;
    color: var(--font-main-color);
    font-size: 16px;
  }
  p {
    font-size: 12px;
    color: var(--font-info-color);
  }
}
.model-icon {
  width: 46px;
  height: 46px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-purple) 10%, transparent);
  display: grid;
  place-items: center;
  color: var(--color-purple);
  font-size: 24px;
}
.model-tabs {
  flex: 1;
  min-height: 0;
  :deep(.intel-tabs-nav) {
    padding: 0 16px;
    margin: 0;
  }
  :deep(.intel-tabs-content-holder) {
    padding: 12px 16px 0;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  :deep(.intel-tabs-content),
  :deep(.intel-tabs-tabpane) {
    height: 100%;
    min-height: 0;
  }
}
.tab-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
</style>
