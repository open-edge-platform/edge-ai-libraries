<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div class="model-detail">
    <div class="configuration-wrap">
      <div class="configuration-header">
        <span>
          <SettingOutlined />
          {{ $t("console.currentConfiguration") }}
        </span>
        <a-tag
          :color="availability.type"
          :bordered="false"
          class="model-availability"
        >
          {{ $t(availability.message) }}
        </a-tag>
      </div>
      <a-descriptions :column="{ xs: 1, md: 2, xl: 3 }" size="small">
        <a-descriptions-item :label="$t('console.modelId')">
          <a-typography-text v-if="modelData.model_id" copyable>
            {{ modelData.model_id }}
          </a-typography-text>
          <span v-else>—</span>
        </a-descriptions-item>
        <a-descriptions-item :label="$t('console.backend')">
          {{ modelData.backend }}
        </a-descriptions-item>
        <a-descriptions-item :label="$t('console.device')">
          <a-tag>{{ modelData.device || "—" }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item
          v-if="modelData.api_base"
          :label="$t('console.apiBase')"
        >
          {{ modelData.api_base }}
        </a-descriptions-item>
        <a-descriptions-item :label="$t('console.modelWorkspace')">
          <span class="path-wrap">{{ modelData.workspace || "—" }}</span>
        </a-descriptions-item>
        <a-descriptions-item
          v-if="modelData.media_model_id"
          :label="$t('console.mediaDefault')"
        >
          {{ modelData.media_model_id }}
        </a-descriptions-item>
      </a-descriptions>
    </div>
    <div class="list-heading">
      <h4>{{ $t("console.availableModels") }}</h4>
      <span>{{ $t("common.total") }}: {{ modelData.models.length }}</span>
    </div>
    <ConsoleTable
      :columns="tableColumns"
      :data-source="modelData.models"
      row-key="name"
      :reset-key="modelData.model_type"
      :scroll="{ x: 650 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <div class="model-name">
            <DeploymentUnitOutlined />
            <strong>{{ record.name }}</strong>
            <a-tag
              v-if="record.name === configuredModel?.name"
              class="theme-tag-primary"
              :bordered="false"
            >
              {{ $t("console.configured") }}
            </a-tag>
          </div>
        </template>
        <template v-else-if="column.key === 'path'">
          <a-typography-text v-if="record.path" copyable class="path-wrap">
            {{ record.path }}
          </a-typography-text>
          <span v-else class="muted-wrap">—</span>
        </template>
        <template v-else-if="column.key === 'state'">
          <a-badge
            v-if="record.ready"
            status="success"
            :text="$t('console.exported')"
          />
          <a-badge v-else status="warning" :text="$t('console.notExported')" />
        </template>
      </template>
    </ConsoleTable>
  </div>
</template>
<script lang="ts" setup name="ModelDetail">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { DeploymentUnitOutlined, SettingOutlined } from "@ant-design/icons-vue";
import type { TableColumnsType } from "ant-design-vue";
import type { ModelInfo, ModelOptions } from "@/api/console/type";
import ConsoleTable from "../../../components/ConsoleTable.vue";
const props = defineProps<{ modelData: ModelOptions }>();
const { t } = useI18n();
const configuredModel = computed(() => {
  const id = props.modelData.model_id;
  if (!id) return undefined;
  const base = id.split("/").pop();
  return (
    props.modelData.models.find((item) => item.name === id) ||
    props.modelData.models.find(
      (item) =>
        item.name.split("/").pop() === base ||
        item.path?.split("/").pop() === base,
    )
  );
});
const availability = computed<{ type: "success" | "error"; message: string }>(
  () => {
    const options = props.modelData;
    const local = options.backend === "local_openvino";
    if (!local)
      return options.api_base
        ? { type: "success", message: "console.remoteConfigured" }
        : { type: "error", message: "console.remoteMissing" };
    if (!configuredModel.value)
      return { type: "error", message: "console.missingModel" };
    return configuredModel.value.ready
      ? { type: "success", message: "console.exported" }
      : { type: "error", message: "console.notExported" };
  },
);
const tableColumns = computed<TableColumnsType<ModelInfo>>(() => [
  { title: t("console.name"), key: "name", dataIndex: "name", width: 350 },
  { title: t("console.modelPath"), key: "path", dataIndex: "path" },
  { title: t("console.status"), key: "state", width: 150 },
]);
</script>
<style scoped lang="less">
.model-detail {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.configuration-wrap {
  flex-shrink: 0;
  border: 1px solid var(--border-main-color);
  border-radius: 8px;
  padding: 12px 16px 4px;
  background: var(--bg-card-color);
}
.model-availability {
  margin-inline-end: 0;
}
.configuration-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
  > span:first-child {
    font-weight: 600;
    color: var(--font-main-color);
  }
  .anticon {
    margin-right: 6px;
  }
}
.list-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 16px 0 10px;
  flex-shrink: 0;
  h4 {
    margin: 0;
    font-size: 14px;
    color: var(--font-main-color);
  }
  span {
    font-size: 12px;
    color: var(--font-info-color);
  }
}
.model-name {
  display: flex;
  align-items: center;
  gap: 10px;
  .anticon {
    color: var(--color-purple);
    font-size: 19px;
  }
  strong {
    font-weight: 500;
  }
}
.path-wrap {
  font-family: monospace;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.muted-wrap {
  color: var(--font-info-color);
}
@media (max-width: 700px) {
  .configuration-wrap {
    max-height: 140px;
    overflow: auto;
  }
}
</style>
