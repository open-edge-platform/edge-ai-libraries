<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <section class="router-detail-module router-config-module" role="tabpanel">
    <div class="router-module-heading">
      <span class="section-icon"><CloudServerOutlined /></span>
      <div>
        <div class="section-title">
          {{ t("router.routerConfigProvidersTitle") }}
        </div>
        <div class="section-caption">
          {{ t("router.routerConfigProvidersCaption") }}
        </div>
      </div>
      <div class="router-module-actions">
        <a-button
          type="text"
          shape="circle"
          size="small"
          :title="t('router.routerReloadConfig')"
          :disabled="isReloading || loading"
          @click="handleReloadConfig"
        >
          <template #icon><ReloadOutlined /></template>
        </a-button>
        <a-button
          type="text"
          shape="circle"
          size="small"
          :title="t('router.refresh')"
          :loading="isReloading || loading"
          @click="handleRefreshData"
        >
          <template #icon><SyncOutlined /></template>
        </a-button>
      </div>
    </div>
    <div v-if="loading" class="router-loading-state">
      {{ t("common.loading") }}
    </div>
    <div class="router-provider-config-list">
      <article
        class="router-provider-config-card router-provider-create-card"
        role="button"
        tabindex="0"
        @click="handleCreate"
        @keydown.enter.prevent="handleCreate"
      >
        <div class="create-card-icon">
          <PlusCircleOutlined />
        </div>
        <div class="create-card-title">
          {{ t("router.routerProviderCreate") }}
        </div>
      </article>
      <article
        v-for="(provider, index) in providerRows"
        :key="`${provider.name || 'provider'}-${index}`"
        class="router-provider-config-card"
        :class="{ enabled: isProviderEnabled(provider) }"
      >
        <div class="router-provider-config-header">
          <div class="router-provider-title-wrap">
            <div class="provider-name-row">
              <span class="provider-name-icon">
                <CloudServerOutlined />
              </span>
              <div class="provider-name-main">
                <strong>{{
                  provider.name ||
                  `${t("router.routerProviderName")} ${index + 1}`
                }}</strong>
                <span class="provider-subtitle">
                  {{ provider.model }}
                </span>
              </div>
            </div>
          </div>
          <span
            class="provider-state-icon is-active"
            v-if="isProviderEnabled(provider)"
          >
            <CheckCircleFilled />
          </span>
        </div>
        <dl class="provider-info-grid">
          <div class="provider-info-item">
            <dt>{{ t("router.routerProviderType") }}</dt>
            <dd>{{ provider.type }}</dd>
          </div>
          <div class="provider-info-item">
            <dt>{{ t("router.routerProviderModel") }}</dt>
            <dd>{{ provider.model }}</dd>
          </div>
          <div class="provider-info-item">
            <dt>{{ t("router.routerProviderEnabled") }}</dt>
            <dd>
              <span
                class="provider-enabled-badge"
                :class="
                  isProviderEnabled(provider) ? 'is-active' : 'is-inactive'
                "
              >
                {{
                  isProviderEnabled(provider) ? t("common.yes") : t("common.no")
                }}
              </span>
            </dd>
          </div>
        </dl>
        <div class="router-provider-card-actions">
          <a-button type="primary" size="small" @click="handleView(provider)">
            <template #icon><EyeOutlined /></template>
            {{ t("common.detail") }}
          </a-button>
          <a-button
            class="intel-btn-warning"
            size="small"
            @click="handleUpdate(provider)"
          >
            <template #icon><EditOutlined /></template>
            {{ t("common.edit") }}
          </a-button>
          <a-button danger size="small" @click="handleDelete(provider)">
            <template #icon><DeleteOutlined /></template>
            {{ t("common.delete") }}
          </a-button>
        </div>
      </article>
      <div v-if="!loading && !providerRows.length" class="router-empty-state">
        {{ t("router.routerNoProviders") }}
      </div>
    </div>
    <ProviderFormDialog
      v-if="updateDialog.visible"
      :dialog-data="updateDialog.data"
      :dialog-type="updateDialog.type"
      @saved="handleDialogSaved"
      @close="updateDialog.visible = false"
    />
    <ProviderDetailDrawer
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
  CheckCircleFilled,
  CloudServerOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusCircleOutlined,
  ReloadOutlined,
  SyncOutlined,
} from "@ant-design/icons-vue";
import {
  deleteRouterProvider,
  getRouterProvider,
  getRouterProviders,
  reloadRouterConfig,
} from "@/api/router";
import { ProviderDetailDrawer, ProviderFormDialog } from "./components";

import type {
  ConfigProviderRow,
  RouterProviderDialogType,
} from "@/views/home/type";

const { t } = useI18n();
const loading = ref(false);
const isReloading = ref(false);
const providerRows = ref<ConfigProviderRow[]>([]);
const updateDialog = reactive<{
  visible: boolean;
  data: ConfigProviderRow;
  type: RouterProviderDialogType;
}>({
  visible: false,
  data: {},
  type: "create",
});
const detailDrawer = reactive<{
  visible: boolean;
  data: ConfigProviderRow;
}>({
  visible: false,
  data: {},
});

const normalizeProviderList = (response: unknown) => {
  const { data, providers } = (response || {}) as Record<string, unknown>;
  if (Array.isArray(data)) return data as ConfigProviderRow[];
  if (Array.isArray(response)) return response as ConfigProviderRow[];
  if (Array.isArray(providers)) return providers as ConfigProviderRow[];
  return [];
};

const normalizeProviderDetail = (response: unknown) => {
  const responseRecord = (response || {}) as Record<string, unknown>;
  const { data } = responseRecord;
  if (data && !Array.isArray(data) && typeof data === "object") {
    return data as ConfigProviderRow;
  }
  return responseRecord;
};

const queryProviderList = async () => {
  loading.value = true;
  try {
    const response = await getRouterProviders();
    providerRows.value = normalizeProviderList(response);
  } catch (error) {
    console.log(error);
  } finally {
    loading.value = false;
  }
};

const getProviderName = (provider: ConfigProviderRow) => {
  const { name = "" } = provider as { name?: unknown };
  return typeof name === "string" ? name : "";
};

const isProviderEnabled = (provider: ConfigProviderRow) => {
  const { enabled = false } = provider as { enabled?: unknown };
  return Boolean(enabled);
};

const queryProviderDetail = async (provider: ConfigProviderRow) => {
  const providerName = getProviderName(provider);
  if (!providerName) return null;
  const response = await getRouterProvider(providerName);
  return normalizeProviderDetail(response);
};

const handleCreate = () => {
  updateDialog.type = "create";
  updateDialog.data = {};
  updateDialog.visible = true;
};

const handleUpdate = async (provider: ConfigProviderRow) => {
  try {
    const providerDetail = await queryProviderDetail(provider);
    if (!providerDetail) return;
    updateDialog.type = "edit";
    updateDialog.data = providerDetail;
    updateDialog.visible = true;
  } catch (error) {
    console.log(error);
  }
};

const handleView = async (provider: ConfigProviderRow) => {
  try {
    const providerDetail = await queryProviderDetail(provider);
    if (!providerDetail) return;
    detailDrawer.data = providerDetail;
    detailDrawer.visible = true;
  } catch (error) {
    console.log(error);
  }
};

const handleDelete = (provider: ConfigProviderRow) => {
  const providerName = getProviderName(provider);
  if (!providerName) return;
  Modal.confirm({
    title: t("common.prompt"),
    content: t("router.routerProviderDeleteConfirmContent", {
      name: providerName,
    }),
    okText: t("common.delete"),
    okType: "danger",
    cancelText: t("common.cancel"),
    async onOk() {
      await deleteRouterProvider(providerName);
      await queryProviderList();
    },
  });
};

const handleReloadConfig = async () => {
  if (isReloading.value) return;
  isReloading.value = true;
  try {
    await reloadRouterConfig();
  } finally {
    isReloading.value = false;
  }
};

const handleRefreshData = async () => {
  if (isReloading.value) return;
  isReloading.value = true;
  try {
    await queryProviderList();
  } finally {
    isReloading.value = false;
  }
};

const handleDialogSaved = async () => {
  updateDialog.visible = false;
  await queryProviderList();
};

onMounted(() => {
  queryProviderList();
});
</script>

<style scoped lang="less">
.router-module-actions {
  gap: 6px;
}
.router-provider-config-card.enabled {
  border-color: color-mix(
    in srgb,
    var(--color-success) 42%,
    var(--border-main-color)
  );
  box-shadow:
    0 22px 40px color-mix(in srgb, var(--color-success) 10%, transparent),
    inset 0 0 0 1px color-mix(in srgb, var(--color-success) 18%, transparent);
}
.create-card-caption {
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
}
.provider-name-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}
.provider-subtitle {
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
  line-height: 1.5;
}
.provider-state-icon,
.provider-enabled-value {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 999px;
  font-size: 18px;
}
.provider-state-icon.is-active,
.provider-enabled-value.is-active {
  background: color-mix(in srgb, var(--color-successSoft) 72%, transparent);
  color: var(--color-success);
}
.provider-state-icon.is-inactive,
.provider-enabled-value.is-inactive {
  background: color-mix(in srgb, var(--font-tip-color) 14%, transparent);
  color: var(--font-tip-color);
}
.provider-enabled-badge {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 6px;
  font-size: var(--font-size-11);
  font-weight: 600;
}
.provider-enabled-badge.is-active {
  background: color-mix(in srgb, var(--color-success) 14%, transparent);
  color: var(--color-success);
}
.provider-enabled-badge.is-inactive {
  background: color-mix(in srgb, var(--font-tip-color) 12%, transparent);
  color: var(--font-tip-color);
}
</style>
