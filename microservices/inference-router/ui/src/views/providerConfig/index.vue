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
          :title="t('router.refresh')"
          :loading="loading"
          @click="handleRefreshData"
        >
          <template #icon><SyncOutlined /></template>
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
      >
        <div class="create-card-icon">
          <PlusCircleOutlined />
        </div>
        <div class="create-card-title">
          {{ t("router.routerProviderCreate") }}
        </div>
      </article>
      <div v-for="provider in providerRows" :key="provider.name">
        <a-badge-ribbon
          class="provider-status-ribbon"
          :class="{ 'is-active': provider.enabled }"
          :text="t('router.routerProviderStatusActive')"
          color="var(--color-success)"
        >
          <article
            class="router-config-card router-provider-config-card"
            :class="{ enabled: provider.enabled }"
          >
            <div class="router-config-card-header">
              <div class="router-config-title-wrap">
                <div class="router-config-name-row provider-name-row">
                  <span class="router-config-name-icon">
                    <CloudServerOutlined />
                  </span>
                  <div class="router-config-name-main">
                    <strong class="router-config-name">
                      {{ provider.name }}
                    </strong>
                    <span class="router-config-subtitle provider-subtitle">
                      {{ provider.model }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
            <dl class="router-config-info-grid">
              <div class="router-config-info-item">
                <dt>{{ t("router.routerProviderType") }}</dt>
                <dd>{{ provider.type }}</dd>
              </div>
              <div class="router-config-info-item">
                <dt>{{ t("router.routerProviderModel") }}</dt>
                <dd>{{ provider.model }}</dd>
              </div>
              <div class="router-config-info-item">
                <dt>{{ t("router.routerProviderEnabled") }}</dt>
                <dd>
                  <span
                    class="provider-enabled-badge"
                    :class="provider.enabled ? 'is-active' : 'is-inactive'"
                  >
                    {{ provider.enabled ? t("common.yes") : t("common.no") }}
                  </span>
                </dd>
              </div>
              <div class="router-config-info-item">
                <dt>{{ t("router.routerProviderFallback") }}</dt>
                <dd>
                  <a-switch
                    size="small"
                    :checked="provider.fallback ?? false"
                    :aria-label="t('router.routerProviderFallback')"
                    @change="handleToggleFallback(provider)"
                  />
                </dd>
              </div>
            </dl>
            <div class="router-config-card-actions router-provider-card-actions">
              <a-button
                type="primary"
                size="small"
                @click="handleView(provider)"
              >
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
        </a-badge-ribbon>
      </div>
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
  CloudServerOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusCircleOutlined,
  SyncOutlined,
} from "@ant-design/icons-vue";
import {
  deleteRouterProvider,
  getRouterProvider,
  getRouterProviders,
  updateRouterProvider,
} from "@/api/providerConfig";
import { ProviderDetailDrawer, ProviderFormDialog } from "./components";

import type {
  ConfigProviderRow,
  RouterProviderDialogType,
} from "@/types/router";

const { t } = useI18n();
const loading = ref(false);
const providerRows = ref<ConfigProviderRow[]>([]);
const updateDialog = reactive<{
  visible: boolean;
  data: ConfigProviderRow;
  type: RouterProviderDialogType;
}>({
  visible: false,
  data: { name: "" },
  type: "create",
});
const detailDrawer = reactive<{
  visible: boolean;
  data: ConfigProviderRow;
}>({
  visible: false,
  data: { name: "" },
});

const queryProviderList = async () => {
  loading.value = true;
  try {
    const { data } = await getRouterProviders();
    providerRows.value = data;
  } catch (error) {
    console.log(error);
  } finally {
    loading.value = false;
  }
};

const queryProviderDetail = async (provider: ConfigProviderRow) => {
  return getRouterProvider(provider.name);
};

const handleToggleFallback = (provider: ConfigProviderRow) => {
  const { name } = provider;
  const fallback = !provider.fallback;
  Modal.confirm({
    title: t(
      fallback
        ? "router.routerProviderEnableFallback"
        : "router.routerProviderDisableFallback",
    ),
    content: t(
      fallback
        ? "router.routerProviderEnableFallbackConfirm"
        : "router.routerProviderDisableFallbackConfirm",
      { name },
    ),
    okText: t("common.confirm"),
    cancelText: t("common.cancel"),
    async onOk() {
      await updateRouterProvider(name, { fallback });
      await queryProviderList();
    },
  });
};

const handleCreate = () => {
  updateDialog.type = "create";
  updateDialog.data = { name: "" };
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
  const { name } = provider;
  Modal.confirm({
    title: t("common.prompt"),
    content: t("router.routerProviderDeleteConfirmContent", {
      name,
    }),
    okText: t("common.delete"),
    okType: "primary",
    okButtonProps: {
      danger: true,
    },
    cancelText: t("common.cancel"),
    async onOk() {
      await deleteRouterProvider(name);
      await queryProviderList();
    },
  });
};

const handleRefreshData = async () => {
  if (loading.value) return;
  await queryProviderList();
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
.router-provider-card-actions {
  flex-wrap: wrap;
}
:deep(.intel-ribbon.provider-status-ribbon) {
  font-size: 11px;
  line-height: 18px;
  padding: 0 5px;
}
:deep(.intel-ribbon.provider-status-ribbon:not(.is-active)) {
  display: none;
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
  align-items: flex-start;
}
.provider-subtitle {
  line-height: 1.5;
}
.provider-enabled-value {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 999px;
  font-size: 18px;
}
.provider-enabled-value.is-active {
  background: color-mix(in srgb, var(--color-successSoft) 72%, transparent);
  color: var(--color-success);
}
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
