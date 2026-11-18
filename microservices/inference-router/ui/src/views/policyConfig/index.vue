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
          {{ t("router.routerPolicyCreate") }}
        </div>
      </article>
      <a-badge-ribbon
        v-for="policy in policyRows"
        :key="policy.name"
        class="policy-status-ribbon"
        :class="{ 'is-active': isActivePolicy(policy) }"
        :text="t('router.routerProviderStatusActive')"
        color="var(--color-success)"
      >
        <article
          class="router-config-card router-policy-config-card"
          :class="{ enabled: isActivePolicy(policy) }"
        >
          <div class="router-config-card-header">
            <div class="router-config-title-wrap">
              <div class="router-config-name-row">
                <span class="router-config-name-icon">
                  <FileProtectOutlined />
                </span>
                <div class="router-config-name-main">
                  <strong class="router-config-name">{{ policy.name }}</strong>
                </div>
              </div>
            </div>
            <div class="policy-activation">
              <a-switch
                v-if="!isActivePolicy(policy)"
                size="small"
                :checked="isActivePolicy(policy)"
                :aria-label="t('router.routerPolicyActivate')"
                :title="
                  t('router.routerPolicyActivateConfirm', {
                    name: policy.name,
                  })
                "
                @change="handleActivatePolicy(policy)"
              />
            </div>
          </div>
          <dl class="router-config-info-grid">
            <div class="router-config-info-item">
              <dt>{{ t("router.routerPolicyCriterion") }}</dt>
              <dd>{{ formatDisplayValue(policy.criterion) }}</dd>
            </div>
            <div class="router-config-info-item">
              <dt>{{ t("router.routerPolicyStrategiesCount") }}</dt>
              <dd>{{ policy.strategies.length }}</dd>
            </div>
          </dl>
          <div class="policy-strategy-tag-panel">
            <div class="policy-strategy-tag-title">
              {{ t("router.routerPolicyStrategies") }}
            </div>
            <div class="policy-strategy-tags">
              <button
                v-for="strategyName in policy.strategies"
                :key="strategyName"
                type="button"
                class="policy-strategy-tag"
                @click="handleViewStrategy(strategyName)"
              >
                {{ strategyName }}
              </button>
              <span
                v-if="!policy.strategies.length"
                class="policy-strategy-tag is-empty"
              >
                {{ t("router.routerPolicyNoStrategies") }}
              </span>
            </div>
          </div>
          <div class="router-config-card-actions">
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
      </a-badge-ribbon>
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
  getRouterRouting,
  updateRouterRouting,
} from "@/api/policyConfig";

import { getRouterStrategy } from "@/api/strategyConfig";
import { formatDisplayValue } from "@/utils/common";
import { PolicyDetailDrawer, PolicyFormDialog } from "./components";
import { StrategyDetailDrawer } from "../strategyConfig/components";
import type {
  PolicyConfigDialogType,
  PolicyConfigRow,
  StrategyConfigRow,
} from "@/types/router";

const { t } = useI18n();
const loading = ref(false);
const isReloading = ref(false);
const policyRows = ref<PolicyConfigRow[]>([]);
const activePolicyName = ref("");
const settingPolicyName = ref("");
const updateDialog = reactive<{
  visible: boolean;
  data: PolicyConfigRow;
  type: PolicyConfigDialogType;
}>({
  visible: false,
  data: { name: "", criterion: "FirstMatch", strategies: [] },
  type: "create",
});
const detailDrawer = reactive<{
  visible: boolean;
  data: PolicyConfigRow;
}>({
  visible: false,
  data: { name: "", criterion: "FirstMatch", strategies: [] },
});
const strategyDetailDrawer = reactive<{
  visible: boolean;
  data: StrategyConfigRow;
}>({
  visible: false,
  data: { name: "" },
});

const queryPolicyList = async () => {
  loading.value = true;
  try {
    policyRows.value = await getRouterPolicies();
  } catch (error) {
    console.log(error);
  } finally {
    loading.value = false;
  }
};

const isActivePolicy = (policy: PolicyConfigRow) => {
  return policy.name === activePolicyName.value;
};

const queryActivePolicy = async () => {
  try {
    const response = await getRouterRouting();
    activePolicyName.value = response.policy ?? "";
  } catch (error) {
    console.error(error);
  }
};

const handleActivatePolicy = (policy: PolicyConfigRow) => {
  const { name } = policy;
  if (isActivePolicy(policy) || settingPolicyName.value) return;

  Modal.confirm({
    title: t("router.routerPolicyActivate"),
    content: t("router.routerPolicyActivateConfirm", { name }),
    okText: t("common.confirm"),
    cancelText: t("common.cancel"),
    async onOk() {
      if (settingPolicyName.value || isActivePolicy(policy)) return;
      settingPolicyName.value = name;
      try {
        await updateRouterRouting({ policy: name });
        await queryActivePolicy();
      } finally {
        settingPolicyName.value = "";
      }
    },
  });
};

const queryPolicyDetail = async (policy: PolicyConfigRow) => {
  return getRouterPolicy(policy.name);
};

const queryStrategyDetail = async (strategyName: string) => {
  if (!strategyName) return null;
  return getRouterStrategy(strategyName);
};

const handleCreate = () => {
  updateDialog.type = "create";
  updateDialog.data = { name: "", criterion: "FirstMatch", strategies: [] };
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
  const { name: policyName } = policy;
  Modal.confirm({
    title: t("common.prompt"),
    content: t("router.routerPolicyDeleteConfirmContent", {
      name: policyName,
    }),
    okText: t("common.delete"),
    okType: "primary",
    okButtonProps: {
      danger: true,
    },
    cancelText: t("common.cancel"),
    async onOk() {
      await deleteRouterPolicy(policyName);
      await Promise.all([queryPolicyList(), queryActivePolicy()]);
    },
  });
};

const handleRefreshData = async () => {
  if (isReloading.value) return;
  isReloading.value = true;
  try {
    await Promise.all([queryPolicyList(), queryActivePolicy()]);
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
  queryActivePolicy();
});
</script>

<style scoped lang="less">
.router-policy-config-card.enabled {
  border-color: color-mix(
    in srgb,
    var(--color-success) 42%,
    var(--border-main-color)
  );
  box-shadow:
    0 22px 40px color-mix(in srgb, var(--color-success) 10%, transparent),
    inset 0 0 0 1px color-mix(in srgb, var(--color-success) 18%, transparent);
}
:deep(.intel-ribbon.policy-status-ribbon:not(.is-active)) {
  display: none;
}
:deep(.intel-ribbon.policy-status-ribbon) {
  font-size: 11px;
  line-height: 18px;
  padding: 0 5px;
}
.policy-activation {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  align-self: center;
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
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  min-width: 0;
  max-width: 100%;
  height: 20px;
  padding: 0 6px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  cursor: pointer;
  font-family: inherit;
  border: 1px solid color-mix(in srgb, var(--color-primary) 22%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-primarySoft) 72%, transparent);
  color: var(--color-primary);
  font-size: var(--font-size-11);
  font-weight: 500;
  line-height: 18px;
}
.policy-strategy-tag:not(:disabled):not(.is-empty):hover {
  cursor: pointer;
  border-color: var(--color-primary);
  background: var(--color-primary);
  color: var(--color-white);
}
.policy-strategy-tag:disabled,
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
