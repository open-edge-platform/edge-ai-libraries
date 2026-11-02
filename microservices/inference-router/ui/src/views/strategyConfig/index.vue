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
      <div class="router-module-actions">
        <a-button
          type="text"
          shape="circle"
          size="small"
          :title="t('router.refresh')"
          :loading="loading"
          @click="handleRefreshData"
        >
          <template #icon><ReloadOutlined /></template>
        </a-button>
      </div>
    </div>
    <div v-if="loading" class="router-loading-state">
      {{ t("common.loading") }}
    </div>
    <div class="router-config-list">
      <article
        class="router-config-card router-config-create-card"
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
        v-for="strategy in strategyRows"
        :key="strategy.name"
        class="router-config-card"
      >
        <div class="router-config-card-header">
          <div class="router-config-title-wrap">
            <div class="router-config-name-row strategy-name-row">
              <span class="router-config-name-icon">
                <BranchesOutlined />
              </span>
              <div class="router-config-name-main">
                <strong class="router-config-name">{{ strategy.name }}</strong>
                <span
                  class="router-config-subtitle multi-ellipsis strategy-subtitle"
                >
                  {{ formatDisplayValue(strategy.description) }}
                </span>
              </div>
            </div>
          </div>
        </div>
        <dl class="router-config-info-grid">
          <div class="router-config-info-item">
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
          <div class="router-config-info-item">
            <dt>{{ t("router.routerStrategyLimit") }}</dt>
            <dd>{{ formatDisplayValue(strategy.limit) }}</dd>
          </div>
        </dl>
        <div class="router-config-card-actions">
          <a-button type="primary" size="small" @click="handleView(strategy)">
            <template #icon><EyeOutlined /></template>
            {{ t("common.detail") }}
          </a-button>
          <a-button
            class="intel-btn-warning"
            size="small"
            @click="handleUpdate(strategy)"
          >
            <template #icon><EditOutlined /></template>
            {{ t("common.edit") }}
          </a-button>
          <a-button danger size="small" @click="handleDelete(strategy)">
            <template #icon><DeleteOutlined /></template>
            {{ t("common.delete") }}
          </a-button>
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
} from "@/api/strategyConfig";
import { formatBooleanText, formatDisplayValue } from "@/utils/common";
import { StrategyDetailDrawer, StrategyFormDialog } from "./components";
import type {
  StrategyConfigDialogType,
  StrategyConfigRow,
} from "@/types/router";

const { t } = useI18n();
const loading = ref(false);
const strategyRows = ref<StrategyConfigRow[]>([]);
const updateDialog = reactive<{
  visible: boolean;
  data: StrategyConfigRow;
  type: StrategyConfigDialogType;
}>({
  visible: false,
  data: { name: "" },
  type: "create",
});
const detailDrawer = reactive<{
  visible: boolean;
  data: StrategyConfigRow;
}>({
  visible: false,
  data: { name: "" },
});

const queryStrategyList = async () => {
  loading.value = true;
  try {
    strategyRows.value = await getRouterStrategies();
  } catch (error) {
    console.log(error);
  } finally {
    loading.value = false;
  }
};

const queryStrategyDetail = async (strategy: StrategyConfigRow) => {
  return getRouterStrategy(strategy.name);
};

const handleCreate = () => {
  updateDialog.type = "create";
  updateDialog.data = { name: "" };
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
  const { name: strategyName } = strategy;
  Modal.confirm({
    title: t("common.prompt"),
    content: t("router.routerStrategyDeleteConfirmContent", {
      name: strategyName,
    }),
    okText: t("common.delete"),
    okType: "primary",
    okButtonProps: {
      danger: true,
    },
    cancelText: t("common.cancel"),
    async onOk() {
      await deleteRouterStrategy(strategyName);
      await queryStrategyList();
    },
  });
};

const handleRefreshData = async () => {
  if (loading.value) return;
  await queryStrategyList();
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
.strategy-name-row {
  align-items: flex-start;
}
.strategy-subtitle {
  white-space: normal;
  line-height: 1.5;
}
</style>
