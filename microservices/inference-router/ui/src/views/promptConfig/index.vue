<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <section class="router-detail-module router-config-module" role="tabpanel">
    <div class="router-module-heading">
      <span class="section-icon"><FileTextOutlined /></span>
      <div>
        <div class="section-title">
          {{ t("router.routerPromptConfigTitle") }}
        </div>
        <div class="section-caption">
          {{ t("router.routerPromptConfigCaption") }}
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
          {{ t("router.routerPromptCreate") }}
        </div>
      </article>
      <div
        v-for="(prompt, index) in promptRows"
        :key="prompt.idx ?? `${prompt.model || 'prompt'}-${index}`"
      >
        <a-badge-ribbon
          class="prompt-status-ribbon"
          :class="{ 'is-active': prompt.active }"
          :text="t('router.routerProviderStatusActive')"
          color="var(--color-success)"
        >
          <article
            class="router-config-card router-prompt-config-card"
            :class="{ active: prompt.active }"
          >
            <div class="router-config-card-header">
              <div class="router-config-title-wrap">
                <div class="router-config-name-row">
                  <span class="router-config-name-icon">
                    <FileTextOutlined />
                  </span>
                  <div class="router-config-name-main">
                    <div class="prompt-title-row">
                      <strong class="router-config-name">
                        Prompt{{ index + 1 }}
                      </strong>
                      <span
                        v-if="prompt.version"
                        class="prompt-version"
                        :title="`${t('router.routerPromptVersion')}: ${prompt.version}`"
                      >
                        <TagOutlined
                          class="prompt-version-icon"
                          aria-hidden="true"
                        />
                        <span class="prompt-version-value">
                          {{ prompt.version }}
                        </span>
                      </span>
                    </div>
                    <span
                      class="router-config-subtitle single-ellipsis"
                      :title="prompt.model"
                    >
                      {{ prompt.model }}
                    </span>
                  </div>
                </div>
              </div>
              <div class="prompt-activation">
                <a-switch
                  size="small"
                  :checked="prompt.active"
                  :aria-label="
                    t(prompt.active ? 'common.deactivate' : 'common.active')
                  "
                  :title="
                    t(prompt.active ? 'common.deactivate' : 'common.active')
                  "
                  @change="handlePromptActiveChange(prompt, $event)"
                />
              </div>
            </div>
            <a-tooltip
              placement="top"
              arrow-point-at-center
              overlay-class-name="router-prompt-content-tooltip"
            >
              <template #title>
                <div>{{ prompt.content }}</div>
              </template>
              <p class="prompt-content">{{ prompt.content }}</p>
            </a-tooltip>
            <div class="router-config-card-actions">
              <a-button type="primary" size="small" @click="handleView(prompt)">
                <template #icon><EyeOutlined /></template>
                {{ t("common.detail") }}
              </a-button>
              <a-button
                class="intel-btn-warning"
                size="small"
                @click="handleUpdate(prompt)"
              >
                <template #icon><EditOutlined /></template>
                {{ t("common.edit") }}
              </a-button>
              <a-button danger size="small" @click="handleDelete(prompt)">
                <template #icon><DeleteOutlined /></template>
                {{ t("common.delete") }}
              </a-button>
            </div>
          </article>
        </a-badge-ribbon>
      </div>
      <div v-if="!loading && !promptRows.length" class="router-empty-state">
        {{ t("router.routerNoPrompts") }}
      </div>
    </div>
    <PromptFormDialog
      v-if="updateDialog.visible"
      :dialog-data="updateDialog.data"
      :dialog-type="updateDialog.type"
      @saved="handleDialogSaved"
      @close="updateDialog.visible = false"
    />
    <PromptDetailDrawer
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
  DeleteOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  FileTextOutlined,
  PlusCircleOutlined,
  SyncOutlined,
  TagOutlined,
} from "@ant-design/icons-vue";
import {
  deleteRouterPrompt,
  getRouterPromptDetail,
  getRouterPrompts,
  updateRouterPrompt,
} from "@/api/promptConfig";
import { PromptDetailDrawer, PromptFormDialog } from "./components";

import type {
  ConfigPromptRow,
  RouterPromptDialogType,
  RouterPromptUpdatePayload,
} from "@/types/router";

const { t } = useI18n();
const loading = ref(false);
const togglingPromptIdx = ref<number | null>(null);
const promptRows = ref<ConfigPromptRow[]>([]);
const updateDialog = reactive<{
  visible: boolean;
  data: ConfigPromptRow;
  type: RouterPromptDialogType;
}>({
  visible: false,
  data: {},
  type: "create",
});
const detailDrawer = reactive<{
  visible: boolean;
  data: ConfigPromptRow;
}>({
  visible: false,
  data: {},
});

const queryPromptList = async () => {
  loading.value = true;
  try {
    promptRows.value = await getRouterPrompts();
  } catch (error) {
    console.log(error);
  } finally {
    loading.value = false;
  }
};

const queryPromptDetail = async (prompt: ConfigPromptRow) => {
  const { idx } = prompt;
  if (typeof idx !== "number") return null;
  return getRouterPromptDetail(idx);
};

const handleCreate = () => {
  updateDialog.type = "create";
  updateDialog.data = {};
  updateDialog.visible = true;
};

const handleUpdate = async (prompt: ConfigPromptRow) => {
  try {
    const promptDetail = await queryPromptDetail(prompt);
    if (!promptDetail) return;
    updateDialog.type = "edit";
    updateDialog.data = promptDetail;
    updateDialog.visible = true;
  } catch (error) {
    console.log(error);
  }
};

const handleView = async (prompt: ConfigPromptRow) => {
  try {
    const promptDetail = await queryPromptDetail(prompt);
    if (!promptDetail) return;
    detailDrawer.data = promptDetail;
    detailDrawer.visible = true;
  } catch (error) {
    console.log(error);
  }
};

const handleDelete = (prompt: ConfigPromptRow) => {
  const { idx: promptIdx } = prompt;
  const promptModel = prompt.model ?? "";
  if (typeof promptIdx !== "number") return;
  Modal.confirm({
    title: t("common.prompt"),
    content: t("router.routerPromptDeleteConfirmContent", {
      model: promptModel,
    }),
    okText: t("common.delete"),
    okType: "primary",
    okButtonProps: {
      danger: true,
    },
    cancelText: t("common.cancel"),
    async onOk() {
      await deleteRouterPrompt(promptIdx);
      await queryPromptList();
    },
  });
};

const handlePromptActiveChange = async (
  prompt: ConfigPromptRow,
  nextActive: boolean,
) => {
  const { idx: promptIdx } = prompt;
  const promptModel = prompt.model ?? "";
  if (typeof promptIdx !== "number" || !promptModel) return;
  if (togglingPromptIdx.value !== null) return;
  if (nextActive === (prompt.active ?? false)) return;

  const payload: RouterPromptUpdatePayload = {
    idx: promptIdx,
    model: promptModel,
    content: prompt.content ?? "",
    active: nextActive,
  };

  togglingPromptIdx.value = promptIdx;
  try {
    await updateRouterPrompt(payload);
    await queryPromptList();
  } catch (error) {
    console.log(error);
  } finally {
    togglingPromptIdx.value = null;
  }
};

const handleRefreshData = async () => {
  if (loading.value) return;
  await queryPromptList();
};

const handleDialogSaved = async () => {
  updateDialog.visible = false;
  await queryPromptList();
};

onMounted(() => {
  queryPromptList();
});
</script>

<style scoped lang="less">
.prompt-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 8px;
  min-width: 0;
}
.prompt-version {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  max-width: 100%;
  padding: 1px 6px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 35%, transparent);
  border-radius: 999px;
  background: linear-gradient(
    120deg,
    var(--color-primary-deep),
    var(--color-purple)
  );
  color: var(--color-white);
  font-size: var(--font-size-11);
  line-height: 14px;
  white-space: nowrap;
}
.prompt-version-icon {
  flex-shrink: 0;
}
.prompt-version-value {
  min-width: 0;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.prompt-content {
  display: -webkit-box;
  max-height: 4.65em;
  margin: 0;
  overflow: hidden;
  color: var(--font-text-color);
  font-size: var(--font-size-12);
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: 3;
}
.router-prompt-config-card.active {
  border-color: color-mix(
    in srgb,
    var(--color-success) 42%,
    var(--border-main-color)
  );
  box-shadow:
    0 22px 40px color-mix(in srgb, var(--color-success) 10%, transparent),
    inset 0 0 0 1px color-mix(in srgb, var(--color-success) 18%, transparent);
}
:deep(.intel-ribbon.prompt-status-ribbon) {
  font-size: 11px;
  line-height: 18px;
  padding: 0 5px;
}
:deep(.intel-ribbon.prompt-status-ribbon:not(.is-active)) {
  display: none;
}
.prompt-activation {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  align-self: center;
}
:global(.router-prompt-content-tooltip) {
  max-width: min(300px, 80vw);
}
:global(.router-prompt-content-tooltip .ant-tooltip-inner) {
  max-height: 50vh;
  overflow-y: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
