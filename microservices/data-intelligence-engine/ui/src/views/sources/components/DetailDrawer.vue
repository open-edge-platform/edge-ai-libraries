<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-drawer
    v-model:open="drawerVisible"
    :title="drawerData.name"
    width="min(700px, 100vw)"
    @close="handleClose"
  >
    <div class="source-heading">
      <div class="source-icon"><DeploymentUnitOutlined /></div>
      <div>
        <StatusTag
          :value="drawerData.reconciled ? 'reconciled' : 'unreconciled'"
        />
        <a-tag :bordered="false">
          {{ $t(`console.${drawerData.type}Source`) }}
        </a-tag>
        <p>{{ drawerData.id }}</p>
      </div>
    </div>
    <a-descriptions bordered :column="1" size="small">
      <a-descriptions-item :label="$t('console.database')">
        {{ drawerData.database_id }}
      </a-descriptions-item>
      <a-descriptions-item :label="$t('console.collection')">
        {{ drawerData.collection_name }}
      </a-descriptions-item>
      <a-descriptions-item :label="$t('console.status')">
        <template v-if="drawerData.enabled">
          {{ $t("console.enabled") }}
        </template>
        <template v-else>{{ $t("console.DISABLED") }}</template>
      </a-descriptions-item>
    </a-descriptions>
    <a-alert
      v-if="drawerData.reconciliation_error"
      type="error"
      showIcon
      :message="drawerData.reconciliation_error"
      class="notice-wrap"
    />
    <a-tabs v-model:activeKey="activeKey">
      <a-tab-pane key="bindings" :tab="$t('console.pools')">
        <a-alert
          v-if="drawerData.type === 'object'"
          type="info"
          showIcon
          :message="$t('console.contentHint')"
        />
        <template v-for="pool in poolList" :key="pool.id">
          <h4>{{ pool.name }}</h4>
          <SourceBinding
            :library-data="libraryData"
            :pool="pool"
            :binding="
              pool.source_statuses.find(
                (item) => item.source_id === drawerData.id,
              )!
            "
            @search="handleSearch"
          />
        </template>
        <a-empty v-if="drawerData.type !== 'object' && !poolList.length" />
      </a-tab-pane>
      <a-tab-pane key="configuration" :tab="$t('console.sourceConfiguration')">
        <div v-if="canChangeDevice" class="device-editor">
          <h4>{{ $t("console.embeddingDevice") }}</h4>
          <div class="device-controls">
            <div class="device-current">
              <span class="device-field-label">{{
                $t("console.currentDevice")
              }}</span>
              <strong>{{
                currentDevice || $t("console.engineDefault")
              }}</strong>
            </div>
            <ArrowRightOutlined class="device-arrow" />
            <div class="device-target">
              <label class="device-field-label">{{
                $t("console.targetDevice")
              }}</label>
              <a-select
                v-model:value="selectedDevice"
                :loading="devicesLoading"
                :disabled="devicesLoading || submitLoading"
                :placeholder="$t('console.pleaseSelect')"
                :options="deviceOptions"
                class="device-select"
              />
            </div>
            <a-button
              class="device-action"
              type="primary"
              :loading="submitLoading"
              :disabled="
                devicesLoading ||
                !selectedDevice ||
                selectedDevice === currentDevice
              "
              @click="handleDeviceChange"
            >
              {{ $t("console.changeDevice") }}
            </a-button>
          </div>
        </div>
        <JsonPretty
          v-if="Object.keys(drawerData.operator_options || {}).length"
          :data="drawerData.operator_options"
          :theme="themeStore.theme === 'dark' ? 'dark' : 'light'"
        />
        <a-empty v-else />
      </a-tab-pane>
    </a-tabs>
    <template v-if="activeKey === 'configuration'" #footer>
      <div class="drawer-footer">
        <div class="console-info-hint footer-hint">
          <InfoCircleOutlined />
          <span>{{ $t("console.sourcesHint") }}</span>
        </div>
      </div>
    </template>
  </a-drawer>
</template>
<script lang="ts" setup name="DetailDrawer">
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Modal } from "ant-design-vue";
import {
  ArrowRightOutlined,
  DeploymentUnitOutlined,
  InfoCircleOutlined,
} from "@ant-design/icons-vue";
import { getModelDevices, requestSourceDeviceUpdate } from "@/api/console";
import type { Library, Source } from "@/api/console/type";
import { themeAppStore } from "@/store/theme";
import JsonPretty from "vue-json-pretty";
import "vue-json-pretty/lib/styles.css";
import StatusTag from "../../../components/StatusTag.vue";
import SourceBinding from "./SourceBinding.vue";
const props = defineProps<{ drawerData: Source; libraryData: Library }>();
const emit = defineEmits<{ close: []; search: [] }>();
const handleClose = () => emit("close");
const handleSearch = () => emit("search");
const { t } = useI18n();
const themeStore = themeAppStore();
const drawerVisible = ref(true);
const activeKey = ref("bindings");
const deviceList = ref<string[]>([]);
const devicesLoading = ref(false);
const submitLoading = ref(false);
const selectedDevice = ref("");
const canChangeDevice = computed(
  () =>
    props.drawerData.type === "vector" &&
    props.drawerData.profile.backend !== "remote_openai_compatible",
);
const currentDevice = computed(() =>
  String(
    props.drawerData.profile.device ||
      props.drawerData.operator_options.embedding_device ||
      "",
  ).toUpperCase(),
);
const deviceOptions = computed(() =>
  [...new Set([currentDevice.value, ...deviceList.value].filter(Boolean))].map(
    (value) => ({ value, label: value }),
  ),
);
watch(
  currentDevice,
  (value) => {
    selectedDevice.value = value;
  },
  { immediate: true },
);
const handleDeviceChange = () => {
  const device = selectedDevice.value;
  if (!device || device === currentDevice.value || submitLoading.value) return;
  Modal.confirm({
    title: t("console.changeDevice"),
    content: t("console.changeDeviceReembed", { device }),
    okText: t("common.confirm"),
    cancelText: t("common.cancel"),
    async onOk() {
      submitLoading.value = true;
      try {
        await requestSourceDeviceUpdate(
          props.libraryData.name,
          props.drawerData.id,
          { embedding_device: device },
        );
        emit("search");
      } finally {
        submitLoading.value = false;
      }
    },
  });
};
onMounted(async () => {
  if (!canChangeDevice.value) return;
  devicesLoading.value = true;
  try {
    deviceList.value = await getModelDevices();
  } finally {
    devicesLoading.value = false;
  }
});
const poolList = computed(() =>
  props.libraryData.asset_pools.filter((pool) =>
    pool.source_statuses.some(
      (status) => status.source_id === props.drawerData.id,
    ),
  ),
);
</script>
<style scoped lang="less">
.source-heading {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 4px 0 24px;
  p {
    margin-top: 8px;
    font-size: 12px;
    font-family: monospace;
    color: var(--font-info-color);
  }
}
.source-icon {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  background: var(--bg-card-color);
  border-radius: 8px;
  font-size: 24px;
  color: var(--color-primary-second);
}
.notice-wrap {
  margin: 20px 0;
}
.drawer-footer {
  display: flex;
  justify-content: flex-end;
}
.footer-hint {
  text-align: right;
}
.device-editor {
  padding: 4px 0 20px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border-main-color);
  h4 {
    margin: 0 0 16px;
  }
}
.device-controls {
  display: grid;
  grid-template-columns: max-content auto minmax(180px, 240px) auto;
  align-items: end;
  justify-content: start;
  gap: 12px;
}
.device-current,
.device-target {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 8px;
}
.device-field-label {
  color: var(--font-info-color);
  font-size: 12px;
}
.device-current strong {
  display: flex;
  width: fit-content;
  max-width: 100%;
  min-height: 32px;
  align-items: center;
  padding: 4px 10px;
  border: 1px solid var(--border-main-color);
  border-radius: 4px;
  background: var(--bg-content-color);
  font-size: 14px;
  overflow-wrap: anywhere;
}
.device-arrow {
  align-self: end;
  margin-bottom: 9px;
  color: var(--font-info-color);
}
.device-select {
  width: 100%;
}
.device-action {
  white-space: nowrap;
}
@media (max-width: 560px) {
  .device-controls {
    grid-template-columns: minmax(0, 96px) auto minmax(0, 1fr);
  }
  .device-action {
    grid-column: 1 / -1;
  }
}
h4 {
  margin: 20px 0 12px;
  color: var(--font-main-color);
  font-weight: 500;
}
</style>
