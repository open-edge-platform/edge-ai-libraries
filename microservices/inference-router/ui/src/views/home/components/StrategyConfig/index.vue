<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <section class="router-detail-module router-strategy-module" role="tabpanel">
    <div class="router-module-heading">
      <span class="section-icon"><BranchesOutlined /></span>
      <div>
        <div class="section-title">
          {{ t("router.routerStrategyConfigTitle") }}
        </div>
        <div class="section-caption">
          {{ t("router.routerStrategyConfigCaption") }}
        </div>
      </div>
      <button
        class="router-icon-action"
        type="button"
        :title="t('router.router')"
        :disabled="isReloading || loading"
        @click="handleRefreshData"
      >
        <ReloadOutlined />
      </button>
    </div>
    <div v-if="loading" class="router-loading-state">
      {{ t("common.loading") }}
    </div>
    <div class="router-strategy-config-list">
      <article
        class="router-strategy-config-card router-strategy-create-card"
        role="button"
        tabindex="0"
        @click="handleCreate"
        @keydown.enter.prevent="handleCreate"
        @keydown.space.prevent="handleCreate"
      >
        <div class="create-card-icon">
          <PlusCircleOutlined />
        </div>
        <div class="create-card-title">
          {{ t("router.routerStrategyCreate") }}
        </div>
      </article>
      <article
        v-for="(strategy, index) in strategyRows"
        :key="`${strategy.name || 'strategy'}-${index}`"
        class="router-strategy-config-card"
      >
        <div class="router-strategy-config-header">
          <div class="router-strategy-title-wrap">
            <div class="strategy-name-row">
              <span class="strategy-name-icon">
                <BranchesOutlined />
              </span>
              <div class="strategy-name-main">
                <strong>{{
                  strategy.name ||
                  `${t("router.routerStrategyName")} ${index + 1}`
                }}</strong>
                <span class="strategy-subtitle">
                  {{ formatDisplayValue(strategy.description) }}
                </span>
              </div>
            </div>
          </div>
        </div>
        <dl class="strategy-info-grid">
          <div class="strategy-info-item">
            <dt>{{ t("router.routerStrategyRequireHealthy") }}</dt>
            <dd>
              {{
                formatBooleanText(
                  strategy.require_healthy,
                  t("common.yes"),
                  t("common.no"),
                )
              }}
            </dd>
          </div>
          <div class="strategy-info-item">
            <dt>{{ t("router.routerStrategyLimit") }}</dt>
            <dd>{{ formatDisplayValue(strategy.limit) }}</dd>
          </div>
        </dl>
        <div class="router-strategy-card-actions">
          <button
            type="button"
            class="router-card-action action-detail"
            @click="handleView(strategy)"
          >
            <EyeOutlined />
            <span>{{ t("common.detail") }}</span>
          </button>
          <button
            type="button"
            class="router-card-action action-edit"
            @click="handleUpdate(strategy)"
          >
            <EditOutlined />
            <span>{{ t("common.edit") }}</span>
          </button>
          <button
            type="button"
            class="router-card-action action-delete"
            @click="handleDelete(strategy)"
          >
            <DeleteOutlined />
            <span>{{ t("common.delete") }}</span>
          </button>
        </div>
      </article>
      <div v-if="!loading && !strategyRows.length" class="router-empty-state">
        {{ t("router.routerNoStrategyConfigs") }}
      </div>
    </div>
    <StrategyFormDialog
      v-if="updateDialog.visible"
      :dialog-data="updateDialog.data"
      :dialog-type="updateDialog.type"
      @saved="handleDialogSaved"
      @close="updateDialog.visible = false"
    />
    <StrategyDetailDrawer
      v-if="detailDrawer.visible"
      :drawer-data="detailDrawer.data"
      @close="detailDrawer.visible = false"
    />
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { Modal } from "ant-design-vue";
import {
  BranchesOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons-vue";
import {
  deleteRouterStrategy,
  getRouterStrategies,
  getRouterStrategy,
} from "@/api/router";
import { formatBooleanText, formatDisplayValue } from "@/utils/common";
import { StrategyDetailDrawer, StrategyFormDialog } from "./components";
import type {
  StrategyConfigDialogType,
  StrategyConfigRow,
} from "@/views/home/type";

const { t } = useI18n();
const loading = ref(false);
const isReloading = ref(false);
const strategyRows = ref<StrategyConfigRow[]>([]);
const updateDialog = reactive<{
  visible: boolean;
  data: StrategyConfigRow;
  type: StrategyConfigDialogType;
}>({
  visible: false,
  data: {},
  type: "create",
});
const detailDrawer = reactive<{
  visible: boolean;
  data: StrategyConfigRow;
}>({
  visible: false,
  data: {},
});

const normalizeStrategyList = (response: unknown) => {
  const { data, strategies } = (response || {}) as Record<string, unknown>;
  if (Array.isArray(data)) return data as StrategyConfigRow[];
  if (Array.isArray(response)) return response as StrategyConfigRow[];
  if (Array.isArray(strategies)) return strategies as StrategyConfigRow[];
  return [];
};

const normalizeStrategyDetail = (response: unknown) => {
  const responseRecord = (response || {}) as Record<string, unknown>;
  const { data } = responseRecord;
  if (data && !Array.isArray(data) && typeof data === "object") {
    return data as StrategyConfigRow;
  }
  return responseRecord;
};

const queryStrategyList = async () => {
  loading.value = true;
  try {
    const response = await getRouterStrategies();
    strategyRows.value = normalizeStrategyList(response);
  } catch (error) {
    console.log(error);
  } finally {
    loading.value = false;
  }
};

const getStrategyName = (strategy: StrategyConfigRow) => {
  const { name = "" } = strategy as { name?: unknown };
  return typeof name === "string" ? name : "";
};

const queryStrategyDetail = async (strategy: StrategyConfigRow) => {
  const strategyName = getStrategyName(strategy);
  if (!strategyName) return null;
  const response = await getRouterStrategy(strategyName);
  return normalizeStrategyDetail(response);
};

const handleCreate = () => {
  updateDialog.type = "create";
  updateDialog.data = {};
  updateDialog.visible = true;
};

const handleUpdate = async (strategy: StrategyConfigRow) => {
  try {
    const strategyDetail = await queryStrategyDetail(strategy);
    if (!strategyDetail) return;
    updateDialog.type = "edit";
    updateDialog.data = strategyDetail;
    updateDialog.visible = true;
  } catch (error) {
    console.log(error);
  }
};

const handleView = async (strategy: StrategyConfigRow) => {
  try {
    const strategyDetail = await queryStrategyDetail(strategy);
    if (!strategyDetail) return;
    detailDrawer.data = strategyDetail;
    detailDrawer.visible = true;
  } catch (error) {
    console.log(error);
  }
};

const handleDelete = (strategy: StrategyConfigRow) => {
  const strategyName = getStrategyName(strategy);
  if (!strategyName) return;
  Modal.confirm({
    title: t("common.prompt"),
    content: t("router.routerStrategyDeleteConfirmContent", {
      name: strategyName,
    }),
    okText: t("common.delete"),
    okType: "danger",
    cancelText: t("common.cancel"),
    async onOk() {
      await deleteRouterStrategy(strategyName);
      await queryStrategyList();
    },
  });
};

const handleRefreshData = async () => {
  if (isReloading.value) return;
  isReloading.value = true;
  try {
    await queryStrategyList();
  } finally {
    isReloading.value = false;
  }
};

const handleDialogSaved = async () => {
  updateDialog.visible = false;
  await queryStrategyList();
};

onMounted(() => {
  queryStrategyList();
});
</script>

<style scoped lang="less">
.router-icon-action {
  margin-left: auto;
}
.strategy-name-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}
.strategy-subtitle {
  display: -webkit-box;
  overflow: hidden;
  text-overflow: ellipsis;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  white-space: normal;
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
  line-height: 1.5;
}
</style>
