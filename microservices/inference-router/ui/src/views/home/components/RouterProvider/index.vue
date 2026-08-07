<template>
  <section class="router-detail-module router-config-module" role="tabpanel">
    <div class="router-module-heading">
      <span class="section-icon"><ToolOutlined /></span>
      <div>
        <div class="section-title">
          {{ t("router.routerConfigProvidersTitle") }}
        </div>
        <div class="section-caption">
          {{ t("router.routerConfigProvidersCaption") }}
        </div>
      </div>
      <button
        class="router-icon-action"
        type="button"
        :title="t('router.routerReloadConfig')"
        :disabled="drawerData.isReloading || loading"
        @click="handleReload"
      >
        <ReloadOutlined />
      </button>
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
                <AppstoreOutlined />
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
            <dd>{{ provider.enabled }}</dd>
          </div>
          <div class="provider-info-item">
            <dt>{{ t("router.routerAvgLatencyMs") }}</dt>
            <dd>
              {{
                drawerData.formatLatencyNullable(
                  resolveProviderLatency(provider),
                )
              }}
            </dd>
          </div>
        </dl>
        <div class="router-provider-card-actions">
          <button
            type="button"
            class="router-card-action action-detail"
            @click="handleView(provider)"
          >
            <EyeOutlined />
            <span>{{ t("common.detail") }}</span>
          </button>
          <button
            type="button"
            class="router-card-action action-edit"
            @click="handleUpdate(provider)"
          >
            <EditOutlined />
            <span>{{ t("common.edit") }}</span>
          </button>
          <button
            type="button"
            class="router-card-action action-delete"
            @click="handleDelete(provider)"
          >
            <DeleteOutlined />
            <span>{{ t("common.delete") }}</span>
          </button>
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
import { computed, onMounted, reactive, ref, watch } from "vue";
import type { PropType } from "vue";
import { useI18n } from "vue-i18n";
import { Modal } from "ant-design-vue";
import {
  AppstoreOutlined,
  CheckCircleFilled,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusCircleOutlined,
  ReloadOutlined,
  ToolOutlined,
} from "@ant-design/icons-vue";
import {
  deleteRouterProvider,
  getRouterProvider,
  getRouterProviders,
} from "@/api/router";
import { ProviderDetailDrawer, ProviderFormDialog } from "./components";

import type {
  ConfigProviderRow,
  LatencyProviderRow,
  RouterProviderDialogType,
} from "@/views/home/type";

interface RouterProviderConfigDrawerData {
  providers: ConfigProviderRow[];
  latencyProviderRows: LatencyProviderRow[];
  isReloading: boolean;
  formatDisplayValue: (value: unknown) => string;
  formatLatencyNullable: (value: number | null) => string;
}

const props = defineProps({
  drawerData: {
    type: Object as PropType<RouterProviderConfigDrawerData>,
    required: true,
    default: () => ({
      providers: [],
      latencyProviderRows: [],
      isReloading: false,
      formatDisplayValue: () => "--",
      formatLatencyNullable: () => "--",
    }),
  },
});

const emit = defineEmits<{ reload: [] }>();

const { t } = useI18n();
const drawerData = computed(() => props.drawerData);
const loading = ref(false);
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
  const responseRecord = response as Record<string, unknown>;
  if (Array.isArray(responseRecord?.data)) {
    return responseRecord.data as ConfigProviderRow[];
  }
  if (Array.isArray(response)) return response as ConfigProviderRow[];
  if (Array.isArray(responseRecord?.providers)) {
    return responseRecord.providers as ConfigProviderRow[];
  }
  return [];
};

const normalizeProviderDetail = (response: unknown) => {
  const responseRecord = response as Record<string, unknown>;
  if (
    responseRecord?.data &&
    !Array.isArray(responseRecord.data) &&
    typeof responseRecord.data === "object"
  ) {
    return responseRecord.data as ConfigProviderRow;
  }
  return responseRecord as ConfigProviderRow;
};

const queryProviderList = async () => {
  loading.value = true;
  try {
    const response = await getRouterProviders();
    providerRows.value = normalizeProviderList(response);
  } catch (error) {
    providerRows.value = drawerData.value.providers;
    console.log(error);
  } finally {
    loading.value = false;
  }
};

const getProviderName = (provider: ConfigProviderRow) =>
  typeof provider.name === "string" ? provider.name : "";

const getProviderModel = (provider: ConfigProviderRow) =>
  typeof provider.model === "string" ? provider.model : "";

const isProviderEnabled = (provider: ConfigProviderRow) =>
  Boolean(provider.enabled);

const resolveProviderLatency = (provider: ConfigProviderRow) => {
  const providerName = getProviderName(provider);
  const providerModel = getProviderModel(provider);
  const providerMetrics = drawerData.value.latencyProviderRows || [];

  const matched = providerMetrics.find((row) => {
    if (row.provider === providerName) return true;
    if (providerName && row.provider.endsWith(`@${providerName}`)) return true;
    if (providerModel && row.provider.startsWith(providerModel)) return true;
    return false;
  });

  return matched?.avgLatencyMs ?? null;
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

const handleReload = async () => {
  emit("reload");
  await queryProviderList();
};

const handleDialogSaved = async () => {
  updateDialog.visible = false;
  await queryProviderList();
};

watch(
  () => drawerData.value.providers,
  (providers) => {
    if (!providerRows.value.length && providers.length)
      providerRows.value = providers;
  },
  { immediate: true },
);

onMounted(() => {
  queryProviderList();
});
</script>

<style scoped lang="less">
.router-detail-module {
  min-width: 0;
  min-height: 100%;
  overflow: visible;
  padding: 0;
  background: transparent;
}
.router-module-heading {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid
    color-mix(in srgb, var(--border-main-color) 78%, transparent);
}
.section-icon,
.router-icon-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.section-icon {
  flex: 0 0 28px;
  width: 28px;
  height: 28px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 22%, transparent);
  background: var(--color-primary);
  color: var(--color-white);
}
.router-icon-action {
  margin-left: auto;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid color-mix(in srgb, var(--color-primary) 20%, transparent);
  border-radius: 7px;
  background: color-mix(
    in srgb,
    var(--color-primary) 8%,
    var(--surface-panel-bg-strong)
  );
  color: var(--color-primary);
  cursor: pointer;
}
.router-icon-action:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.router-primary-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  min-height: 28px;
  padding: 0 10px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 24%, transparent);
  border-radius: 7px;
  background: var(--color-primary);
  color: var(--color-white);
  font-size: var(--font-size-12);
  cursor: pointer;
}
.router-primary-action + .router-icon-action {
  margin-left: 0;
}
.section-title {
  font-size: var(--font-size-13);
  font-weight: 600;
}
.section-caption {
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
}
.router-provider-config-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 320px));
  justify-content: center;
  gap: 10px;
  min-height: 0;
  padding-right: 2px;
  padding-bottom: 2px;
}
.router-provider-config-card {
  display: grid;
  gap: 14px;
  min-width: 0;
  width: 100%;
  max-width: 320px;
  padding: 16px;
  border: 1px solid
    color-mix(in srgb, var(--color-white) 6%, var(--border-main-color));
  border-radius: 18px;
  background: color-mix(
    in srgb,
    var(--surface-card-bg) 82%,
    var(--surface-panel-bg-strong) 18%
  );
  box-shadow:
    0 18px 36px color-mix(in srgb, var(--bg-box-shadow) 72%, transparent),
    inset 0 1px 0 color-mix(in srgb, var(--color-white) 12%, transparent);
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}
.router-provider-config-card:hover {
  transform: translateY(-2px);
  box-shadow:
    0 22px 38px color-mix(in srgb, var(--bg-box-shadow) 86%, transparent),
    inset 0 1px 0 color-mix(in srgb, var(--color-white) 14%, transparent);
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
.router-provider-create-card {
  place-content: center;
  text-align: center;
  gap: 12px;
  cursor: pointer;
  border-style: dashed;
  border-color: color-mix(in srgb, var(--color-primary) 40%, transparent);
  background:
    radial-gradient(
      circle at top,
      color-mix(in srgb, var(--color-primarySoft) 52%, transparent),
      transparent 68%
    ),
    color-mix(in srgb, var(--surface-card-bg) 82%, var(--color-primarySoft) 18%);
}
.router-provider-create-card:hover {
  border-color: color-mix(in srgb, var(--color-primary) 62%, transparent);
  box-shadow: 0 8px 22px
    color-mix(in srgb, var(--color-primary) 18%, transparent);
}
.create-card-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  margin: 0 auto;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-primary) 14%, transparent);
  color: var(--color-primary);
  font-size: 22px;
}
.create-card-title {
  color: var(--font-main-color);
  font-size: var(--font-size-14);
  font-weight: 600;
}
.create-card-caption {
  color: var(--font-tip-color);
  font-size: var(--font-size-11);
}
.router-provider-config-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.router-provider-config-header strong {
  color: var(--font-main-color);
  font-size: var(--font-size-14);
  font-weight: 600;
}
.router-provider-title-wrap {
  display: block;
  min-width: 0;
}
.provider-name-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}
.provider-name-main {
  display: grid;
  gap: 4px;
  min-width: 0;
}
.provider-name-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 38px;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 14%, transparent);
  font-size: 18px;
}
.router-provider-title-wrap strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
.provider-info-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
  margin: 0;
  padding: 0;
}
.provider-info-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
  padding: 0;
}
.provider-info-item dt {
  flex: 1;
  min-width: 0;
  color: var(--font-text-color);
  font-size: var(--font-size-11);
  font-weight: 500;
}
.provider-info-item dd {
  margin: 0;
  max-width: 55%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--font-main-color);
  font-size: var(--font-size-12);
  font-weight: 500;
  text-align: right;
}
.router-provider-card-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  margin-top: auto;
  padding-top: 4px;
}
.router-card-action {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 28px;
  padding: 0 12px;
  border: none;
  border-radius: 9px;
  color: var(--color-white);
  font-size: var(--font-size-12);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}
.router-card-action.action-detail {
  background: var(--color-primary);
}
.router-card-action.action-detail:hover {
  background: var(--color-primary-hover);
}
.router-card-action.action-edit {
  background: var(--color-warning-strong);
}
.router-card-action.action-edit:hover {
  background: var(--color-warning-hover);
}
.router-card-action.action-delete {
  background: var(--color-error);
}
.router-card-action.action-delete:hover {
  background: var(--color-error-hover);
}
.router-loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 72px;
  margin-bottom: 10px;
  border: 1px dashed
    color-mix(in srgb, var(--border-main-color) 70%, transparent);
  border-radius: 12px;
  color: var(--font-tip-color);
  font-size: var(--font-size-12);
}
.router-empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  width: 100%;
  border: 1px dashed
    color-mix(in srgb, var(--border-main-color) 70%, transparent);
  border-radius: 12px;
  color: var(--font-tip-color);
  font-size: var(--font-size-12);
}
</style>
