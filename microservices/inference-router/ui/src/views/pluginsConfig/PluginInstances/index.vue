<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <div v-if="loading" class="router-loading-state">
    {{ t("common.loading") }}
  </div>
  <div class="router-config-list plugin-card-list">
    <article
      class="router-config-card plugin-create-card"
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
    <div v-for="plugin in pluginRows" :key="`${plugin.node}-${plugin.name}`">
      <a-badge-ribbon
        class="plugin-status-ribbon"
        :class="{ 'is-active': plugin.enabled }"
        :text="t('router.routerProviderStatusActive')"
        color="var(--color-success)"
      >
        <article
          class="router-config-card plugin-card"
          :class="{ enabled: plugin.enabled }"
        >
          <div class="router-config-card-header plugin-card-header">
            <span class="router-config-name-icon plugin-card-icon">
              <ApiOutlined />
            </span>
            <div class="router-config-name-main">
              <strong class="router-config-name plugin-card-name">
                {{ plugin.name }}
              </strong>
              <span class="router-config-subtitle single-ellipsis">
                {{ plugin.node }}
              </span>
            </div>
          </div>
          <dl class="router-config-info-grid">
            <div class="router-config-info-item">
              <dt>{{ t("router.routerPluginTrigger") }}</dt>
              <dd>{{ plugin.trigger }}</dd>
            </div>
            <div class="router-config-info-item">
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
          <div class="router-config-card-actions plugin-card-actions">
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
      </a-badge-ribbon>
    </div>
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
} from "@/api/pluginsConfig";
import { PluginFormDialog, PluginInstanceDetailDrawer } from "./components";
import type { ConfigPluginRow, RouterPluginDialogType } from "@/types/router";

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

const queryPluginData = async () => {
  loading.value = true;
  try {
    const { data } = await getRouterPlugins();
    pluginRows.value = data;
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
    const pluginDetail = await getRouterPlugin(plugin.node, plugin.name);
    if (!pluginDetail) return;
    updateDialog.data = pluginDetail;
    updateDialog.type = "edit";
    updateDialog.visible = true;
  } catch (error) {
    console.log(error);
  }
};

const handleView = async (plugin: ConfigPluginRow) => {
  try {
    const pluginDetail = await getRouterPlugin(plugin.node, plugin.name);
    if (!pluginDetail) return;
    detailDrawer.data = pluginDetail;
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
    okType: "primary",
    okButtonProps: {
      danger: true,
    },
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
  padding-right: 0;
  padding-bottom: 0;
}
.plugin-card.enabled {
  border-color: color-mix(
    in srgb,
    var(--color-success) 42%,
    var(--border-main-color)
  );
}
:deep(.intel-ribbon.plugin-status-ribbon) {
  font-size: 11px;
  line-height: 18px;
  padding: 0 5px;
}
:deep(.intel-ribbon.plugin-status-ribbon:not(.is-active)) {
  display: none;
}
.plugin-create-card {
  place-content: center;
  text-align: center;
  cursor: pointer;
  border-style: dashed;
  border-color: color-mix(in srgb, var(--color-primary) 40%, transparent);
}
.plugin-card-header {
  justify-content: normal;
  gap: 9px;
  min-width: 0;
}
.plugin-card-icon {
  border-radius: 8px;
}
.plugin-card-name {
  font-weight: bolder;
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
@media (max-width: 720px) {
  .plugin-card-actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .plugin-card-actions .intel-btn {
    width: 100%;
  }
}
</style>
