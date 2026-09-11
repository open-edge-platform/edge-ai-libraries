<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <section class="router-detail-module router-policy-module" role="tabpanel">
    <div class="router-module-heading">
      <span class="section-icon"><FileProtectOutlined /></span>
      <div>
        <div class="section-title">
          {{ t("router.routerPolicyConfigTitle") }}
        </div>
        <div class="section-caption">
          {{ t("router.routerPolicyConfigCaption") }}
        </div>
      </div>
      <div class="router-module-actions">
        <a-button
          type="text"
          shape="circle"
          size="small"
          :title="t('router.refresh')"
          :loading="isReloading || loading"
          @click="handleRefreshData"
        >
          <template #icon><ReloadOutlined /></template>
        </a-button>
      </div>
    </div>
    <div v-if="loading" class="router-loading-state">
      {{ t("common.loading") }}
    </div>
    <div class="router-policy-config-list">
      <article
        class="router-policy-config-card router-policy-create-card"
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
          {{ t("router.routerPolicyCreate") }}
        </div>
      </article>
      <article
        v-for="(policy, index) in policyRows"
        :key="`${policy.name || 'policy'}-${index}`"
        class="router-policy-config-card"
      >
        <div class="router-policy-config-header">
          <div class="router-policy-title-wrap">
            <div class="policy-name-row">
              <span class="policy-name-icon">
                <FileProtectOutlined />
              </span>
              <div class="policy-name-main">
                <strong>{{
                  policy.name || `${t("router.routerPolicyName")} ${index + 1}`
                }}</strong>
              </div>
            </div>
          </div>
        </div>
        <dl class="policy-info-grid">
          <div class="policy-info-item">
            <dt>{{ t("router.routerPolicyCriterion") }}</dt>
            <dd>{{ formatDisplayValue(policy.criterion) }}</dd>
          </div>
          <div class="policy-info-item">
            <dt>{{ t("router.routerPolicyStrategiesCount") }}</dt>
            <dd>{{ getStrategyNames(policy.strategies).length }}</dd>
          </div>
        </dl>
        <div class="policy-strategy-tag-panel">
          <div class="policy-strategy-tag-title">
            {{ t("router.routerPolicyStrategies") }}
          </div>
          <div class="policy-strategy-tags">
            <a-button
              v-for="strategyName in getStrategyNames(policy.strategies)"
              :key="strategyName"
              type="link"
              size="small"
              class="policy-strategy-tag"
              @click="handleViewStrategy(strategyName)"
            >
              {{ strategyName }}
            </a-button>
            <span
              v-if="!getStrategyNames(policy.strategies).length"
              class="policy-strategy-tag is-empty"
            >
              {{ t("router.routerPolicyNoStrategies") }}
            </span>
          </div>
        </div>
        <div class="router-policy-card-actions">
          <a-button type="primary" size="small" @click="handleView(policy)">
            <template #icon><EyeOutlined /></template>
            {{ t("common.detail") }}
          </a-button>
          <a-button
            class="intel-btn-warning"
            size="small"
            @click="handleUpdate(policy)"
          >
            <template #icon><EditOutlined /></template>
            {{ t("common.edit") }}
          </a-button>
          <a-button danger size="small" @click="handleDelete(policy)">
            <template #icon><DeleteOutlined /></template>
            {{ t("common.delete") }}
          </a-button>
        </div>
      </article>
      <div v-if="!loading && !policyRows.length" class="router-empty-state">
        {{ t("router.routerNoPolicyConfigs") }}
      </div>
    </div>
    <PolicyFormDialog
      v-if="updateDialog.visible"
      :dialog-data="updateDialog.data"
      :dialog-type="updateDialog.type"
      @saved="handleDialogSaved"
      @close="updateDialog.visible = false"
    />
    <PolicyDetailDrawer
      v-if="detailDrawer.visible"
      :drawer-data="detailDrawer.data"
      @view-strategy="handleViewStrategy"
      @close="detailDrawer.visible = false"
    />
    <StrategyDetailDrawer
      v-if="strategyDetailDrawer.visible"
      :drawer-data="strategyDetailDrawer.data"
      @close="strategyDetailDrawer.visible = false"
    />
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { Modal } from "ant-design-vue";
import {
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  FileProtectOutlined,
  PlusCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons-vue";
import {
  deleteRouterPolicy,
  getRouterPolicies,
  getRouterPolicy,
  getRouterStrategy,
} from "@/api/router";
import { formatDisplayValue } from "@/utils/common";
import { PolicyDetailDrawer, PolicyFormDialog } from "./components";
import { StrategyDetailDrawer } from "../StrategyConfig/components";
import type {
  PolicyConfigDialogType,
  PolicyConfigRow,
  StrategyConfigRow,
} from "@/views/home/type";

const { t } = useI18n();
const loading = ref(false);
const isReloading = ref(false);
const policyRows = ref<PolicyConfigRow[]>([]);
const updateDialog = reactive<{
  visible: boolean;
  data: PolicyConfigRow;
  type: PolicyConfigDialogType;
}>({
  visible: false,
  data: {},
  type: "create",
});
const detailDrawer = reactive<{
  visible: boolean;
  data: PolicyConfigRow;
}>({
  visible: false,
  data: {},
});
const strategyDetailDrawer = reactive<{
  visible: boolean;
  data: StrategyConfigRow;
}>({
  visible: false,
  data: {},
});

const normalizePolicyList = (response: unknown) => {
  const { data, policies } = (response || {}) as Record<string, unknown>;
  if (Array.isArray(data)) return data as PolicyConfigRow[];
  if (Array.isArray(response)) return response as PolicyConfigRow[];
  if (Array.isArray(policies)) return policies as PolicyConfigRow[];
  return [];
};

const normalizePolicyDetail = (response: unknown) => {
  const responseRecord = (response || {}) as Record<string, unknown>;
  const { data } = responseRecord;
  if (data && !Array.isArray(data) && typeof data === "object") {
    return data as PolicyConfigRow;
  }
  return responseRecord;
};

const normalizeStrategyDetail = (response: unknown) => {
  const responseRecord = (response || {}) as Record<string, unknown>;
  const { data } = responseRecord;
  if (data && !Array.isArray(data) && typeof data === "object") {
    return data as StrategyConfigRow;
  }
  return responseRecord;
};

const getStrategyNames = (strategies: unknown) => {
  return Array.isArray(strategies)
    ? strategies.filter(
        (strategy): strategy is string => typeof strategy === "string",
      )
    : [];
};

const queryPolicyList = async () => {
  loading.value = true;
  try {
    const response = await getRouterPolicies();
    policyRows.value = normalizePolicyList(response);
  } catch (error) {
    console.log(error);
  } finally {
    loading.value = false;
  }
};

const getPolicyName = (policy: PolicyConfigRow) => {
  const { name = "" } = policy as { name?: unknown };
  return typeof name === "string" ? name : "";
};

const queryPolicyDetail = async (policy: PolicyConfigRow) => {
  const policyName = getPolicyName(policy);
  if (!policyName) return null;
  const response = await getRouterPolicy(policyName);
  return normalizePolicyDetail(response);
};

const queryStrategyDetail = async (strategyName: string) => {
  if (!strategyName) return null;
  const response = await getRouterStrategy(strategyName);
  return normalizeStrategyDetail(response);
};

const handleCreate = () => {
  updateDialog.type = "create";
  updateDialog.data = {};
  updateDialog.visible = true;
};

const handleUpdate = async (policy: PolicyConfigRow) => {
  try {
    const policyDetail = await queryPolicyDetail(policy);
    if (!policyDetail) return;
    updateDialog.type = "edit";
    updateDialog.data = policyDetail;
    updateDialog.visible = true;
  } catch (error) {
    console.log(error);
  }
};

const handleView = async (policy: PolicyConfigRow) => {
  try {
    const policyDetail = await queryPolicyDetail(policy);
    if (!policyDetail) return;
    detailDrawer.data = policyDetail;
    detailDrawer.visible = true;
  } catch (error) {
    console.log(error);
  }
};

const handleViewStrategy = async (strategyName: string) => {
  try {
    const strategyDetail = await queryStrategyDetail(strategyName);
    if (!strategyDetail) return;
    strategyDetailDrawer.data = strategyDetail;
    strategyDetailDrawer.visible = true;
  } catch (error) {
    console.log(error);
  }
};

const handleDelete = (policy: PolicyConfigRow) => {
  const policyName = getPolicyName(policy);
  if (!policyName) return;
  Modal.confirm({
    title: t("common.prompt"),
    content: t("router.routerPolicyDeleteConfirmContent", {
      name: policyName,
    }),
    okText: t("common.delete"),
    okType: "danger",
    cancelText: t("common.cancel"),
    async onOk() {
      await deleteRouterPolicy(policyName);
      await queryPolicyList();
    },
  });
};

const handleRefreshData = async () => {
  if (isReloading.value) return;
  isReloading.value = true;
  try {
    await queryPolicyList();
  } finally {
    isReloading.value = false;
  }
};

const handleDialogSaved = async () => {
  updateDialog.visible = false;
  await queryPolicyList();
};

onMounted(() => {
  queryPolicyList();
});
</script>

<style scoped lang="less">
.policy-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.policy-subtitle {
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
  line-height: 1.5;
}
.policy-strategy-tag-panel {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}
.policy-strategy-tag-title {
  flex: 0 0 auto;
  color: var(--font-text-color);
  font-size: var(--font-size-11);
  font-weight: 600;
  line-height: 20px;
}
.policy-strategy-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  flex: 1;
  min-width: 0;
}
.policy-strategy-tag {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  max-width: 100%;
  min-height: 20px;
  padding: 0 6px;
  cursor: pointer;
  border: 1px solid color-mix(in srgb, var(--color-primary) 22%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-primarySoft) 72%, transparent);
  color: var(--color-primary);
  font-size: var(--font-size-10);
  font-weight: 600;
  line-height: 1;
}
.policy-strategy-tag:hover {
  border-color: color-mix(in srgb, var(--color-primary) 50%, transparent);
  background: color-mix(in srgb, var(--color-primarySoft) 86%, transparent);
}
.policy-strategy-tag.is-empty {
  cursor: default;
  border-color: color-mix(in srgb, var(--border-main-color) 72%, transparent);
  background: color-mix(
    in srgb,
    var(--surface-panel-bg-strong) 82%,
    transparent
  );
  color: var(--font-tip-color);
}
</style>
