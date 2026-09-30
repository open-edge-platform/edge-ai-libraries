<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <div v-if="loading" class="router-loading-state">
    {{ t("common.loading") }}
  </div>
  <div class="plugin-card-list">
    <article
      class="plugin-card plugin-create-card"
      role="button"
      tabindex="0"
      @click="handleCreate()"
      @keydown.enter.prevent="handleCreate()"
    >
      <PlusCircleOutlined class="create-card-icon" />
      <div class="create-card-title">
        {{ t("router.routerPluginCreate") }}
      </div>
    </article>
    <article
      v-for="plugin in pluginRows"
      :key="`${plugin.node}-${plugin.name}`"
      class="plugin-card"
      :class="{ enabled: plugin.enabled }"
    >
      <div class="plugin-card-header">
        <span class="plugin-card-icon"><ApiOutlined /></span>
        <div class="plugin-card-title">
          <strong>{{ plugin.name }}</strong>
          <span>{{ plugin.node }}</span>
        </div>
        <CheckCircleFilled v-if="plugin.enabled" class="plugin-enabled-icon" />
      </div>
      <dl class="plugin-info-grid">
        <div>
          <dt>{{ t("router.routerPluginTrigger") }}</dt>
          <dd>{{ plugin.trigger }}</dd>
        </div>
        <div>
          <dt>{{ t("router.routerPluginEnabled") }}</dt>
          <dd>
            <span
              class="plugin-status"
              :class="plugin.enabled ? 'is-enabled' : 'is-disabled'"
            >
              {{ plugin.enabled ? t("common.yes") : t("common.no") }}
            </span>
          </dd>
        </div>
      </dl>
      <div class="plugin-card-actions">
        <a-button type="primary" size="small" @click="handleView(plugin)">
          <template #icon><EyeOutlined /></template>
          {{ t("common.detail") }}
        </a-button>
        <a-button
          class="intel-btn-warning"
          size="small"
          @click="handleUpdate(plugin)"
        >
          <template #icon><EditOutlined /></template>
          {{ t("common.edit") }}
        </a-button>
        <a-button
          size="small"
          :title="
            plugin.enabled
              ? t('common.reset')
              : t('router.routerPluginResetDisabledTip')
          "
          :disabled="!plugin.enabled"
          @click="handleReset(plugin)"
        >
          <template #icon><UndoOutlined /></template>
          {{ t("common.reset") }}
        </a-button>
        <a-button danger size="small" @click="handleDelete(plugin)">
          <template #icon><DeleteOutlined /></template>
          {{ t("common.delete") }}
        </a-button>
      </div>
    </article>
    <div v-if="!loading && !pluginRows.length" class="router-empty-state">
      {{ t("router.routerNoPlugins") }}
    </div>
  </div>

  <PluginFormDialog
    v-if="updateDialog.visible"
    :dialog-data="updateDialog.data"
    :dialog-type="updateDialog.type"
    @saved="handleDialogSaved"
    @close="updateDialog.visible = false"
  />
  <PluginInstanceDetailDrawer
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
  ApiOutlined,
  CheckCircleFilled,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusCircleOutlined,
  UndoOutlined,
} from "@ant-design/icons-vue";
import {
  deleteRouterPlugin,
  getRouterPlugin,
  getRouterPlugins,
  resetRouterPlugin,
} from "@/api/router";
import { PluginFormDialog, PluginInstanceDetailDrawer } from "./components";
import type {
  ConfigPluginRow,
  RouterPluginDialogType,
} from "@/views/home/type";

const { t } = useI18n();
const loading = ref(false);
const pluginRows = ref<ConfigPluginRow[]>([]);
const updateDialog = reactive<{
  visible: boolean;
  data: Partial<ConfigPluginRow>;
  type: RouterPluginDialogType;
}>({ visible: false, data: {}, type: "create" });
const detailDrawer = reactive({
  visible: false,
  data: {} as ConfigPluginRow,
});

const normalizeList = <T,>(response: unknown) => {
  if (Array.isArray(response)) return response as T[];
  const { data } = (response || {}) as { data?: unknown };
  return Array.isArray(data) ? (data as T[]) : [];
};

const normalizeDetail = (response: unknown) => {
  const responseRecord = (response || {}) as Record<string, unknown>;
  const { data } = responseRecord;
  if (data && !Array.isArray(data) && typeof data === "object") {
    return data as ConfigPluginRow;
  }
  return responseRecord as ConfigPluginRow;
};

const queryPluginData = async () => {
  loading.value = true;
  try {
    const pluginsResponse = await getRouterPlugins();
    pluginRows.value = normalizeList<ConfigPluginRow>(pluginsResponse);
  } catch (error) {
    console.log(error);
  } finally {
    loading.value = false;
  }
};

const handleCreate = (node?: string) => {
  updateDialog.type = "create";
  updateDialog.data = node ? { node } : {};
  updateDialog.visible = true;
};

const handleUpdate = async (plugin: ConfigPluginRow) => {
  try {
    updateDialog.data = normalizeDetail(
      await getRouterPlugin(plugin.node, plugin.name),
    );
    updateDialog.type = "edit";
    updateDialog.visible = true;
  } catch (error) {
    console.log(error);
  }
};

const handleView = async (plugin: ConfigPluginRow) => {
  try {
    detailDrawer.data = normalizeDetail(
      await getRouterPlugin(plugin.node, plugin.name),
    );
    detailDrawer.visible = true;
  } catch (error) {
    console.log(error);
  }
};

const handleDelete = (plugin: ConfigPluginRow) => {
  Modal.confirm({
    title: t("common.prompt"),
    content: t("router.routerPluginDeleteConfirmContent", {
      name: plugin.name,
    }),
    okText: t("common.delete"),
    okType: "danger",
    cancelText: t("common.cancel"),
    async onOk() {
      await deleteRouterPlugin(plugin.node, plugin.name);
      await queryPluginData();
    },
  });
};

const handleReset = (plugin: ConfigPluginRow) => {
  Modal.confirm({
    title: t("common.prompt"),
    content: t("router.routerPluginResetConfirmContent", { name: plugin.name }),
    okText: t("common.reset"),
    cancelText: t("common.cancel"),
    async onOk() {
      await resetRouterPlugin(plugin.node, plugin.name);
    },
  });
};

const handleDialogSaved = async () => {
  updateDialog.visible = false;
  await queryPluginData();
};

defineExpose({ refresh: queryPluginData });
onMounted(queryPluginData);
</script>

<style scoped lang="less">
.plugin-card-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 380px));
  justify-content: start;
  gap: 16px;
}
.plugin-card {
  display: grid;
  gap: 14px;
  min-height: 210px;
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
.plugin-card.enabled {
  border-color: color-mix(
    in srgb,
    var(--color-success) 42%,
    var(--border-main-color)
  );
}
.plugin-create-card {
  place-content: center;
  text-align: center;
  cursor: pointer;
  border-style: dashed;
  border-color: color-mix(in srgb, var(--color-primary) 40%, transparent);
}
.plugin-card-header {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  min-width: 0;
}
.plugin-card-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 38px;
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-primary) 14%, transparent);
  color: var(--color-primary);
  font-size: 18px;
}
.plugin-card-title {
  display: grid;
  gap: 4px;
  min-width: 0;
}
.plugin-card-title strong,
.plugin-card-title span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.plugin-card-title strong {
  color: var(--font-main-color);
  font-size: var(--font-size-14);
}
.plugin-card-title span {
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
}
.plugin-enabled-icon {
  margin-left: auto;
  color: var(--color-success);
  font-size: 18px;
}
.plugin-info-grid {
  display: grid;
  gap: 8px;
  margin: 0;
}
.plugin-info-grid div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.plugin-info-grid dt {
  color: var(--font-text-color);
  font-size: var(--font-size-11);
}
.plugin-info-grid dd {
  margin: 0;
  color: var(--font-main-color);
  font-size: var(--font-size-12);
}
.plugin-status {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 6px;
  font-size: var(--font-size-11);
  font-weight: 600;
}
.plugin-status.is-enabled {
  background: color-mix(in srgb, var(--color-success) 14%, transparent);
  color: var(--color-success);
}
.plugin-status.is-disabled {
  background: color-mix(in srgb, var(--font-tip-color) 12%, transparent);
  color: var(--font-tip-color);
}
.plugin-card-actions {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  justify-content: flex-end;
  gap: 8px;
  margin-top: auto;
}
@media (max-width: 720px) {
  .plugin-card-list {
    grid-template-columns: minmax(0, 1fr);
  }
  .plugin-card-actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .plugin-card-actions .intel-btn {
    width: 100%;
  }
}
</style>
