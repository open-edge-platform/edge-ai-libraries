<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-drawer
    v-model:open="drawerVisible"
    :title="drawerData.name"
    width="min(780px, 100vw)"
    @close="handleClose"
  >
    <div class="detail-header">
      <div class="pool-icon"><ApartmentOutlined /></div>
      <div>
        <div class="pool-id">{{ drawerData.id }}</div>
        <StatusTag :value="drawerData.display_status" />
      </div>
      <a-button type="primary" ghost @click="handleRetrieve">
        <template #icon><SearchOutlined /></template>
        {{ $t("console.retrieve") }}
      </a-button>
    </div>
    <a-row :gutter="16" class="stats-wrap">
      <a-col :span="8">
        <a-statistic
          :title="$t('console.assets')"
          :value="drawerData.asset_ids.length"
        />
      </a-col>
      <a-col :span="8">
        <a-statistic
          :title="$t('console.sources')"
          :value="drawerData.source_statuses.length"
        />
      </a-col>
      <a-col :span="8">
        <a-statistic
          :title="$t('console.revision')"
          :value="drawerData.revision"
        />
      </a-col>
    </a-row>
    <a-tabs v-model:activeKey="activeKey">
      <a-tab-pane key="sources" :tab="$t('console.poolSources')">
        <p class="section-hint">{{ $t("console.servingHint") }}</p>
        <SourceBinding
          v-for="binding in drawerData.source_statuses"
          :key="binding.source_id"
          :library-data="libraryData"
          :pool="drawerData"
          :binding="binding"
          @search="handleSearch"
        />
        <div class="edit-section">
          <h4>
            {{ $t("console.saveSources") }}
            <FormTooltip :title="$t('console.poolBindingHint')" />
          </h4>
          <a-select
            v-model:value="sourceIds"
            :placeholder="$t('console.pleaseSelect')"
            mode="multiple"
            class="full-width"
            :options="
              sourceList.map((item) => ({
                value: item.id,
                label: `${item.name} (${item.type})`,
              }))
            "
          />
          <a-button
            type="primary"
            :loading="submitLoading"
            :disabled="!sourceIds.length"
            @click="handleSaveSources"
          >
            {{ $t("common.save") }}
          </a-button>
        </div>
      </a-tab-pane>
      <a-tab-pane key="assets" :tab="$t('console.poolAssets')">
        <div class="asset-actions">
          <FormTooltip :title="$t('console.poolAssetsHint')" />
          <a-select
            v-model:value="assetIds"
            mode="multiple"
            showSearch
            optionFilterProp="label"
            :maxTagCount="2"
            :placeholder="$t('console.pleaseSelect')"
            :options="
              assetList
                .filter((item) => !item.pending && !poolAssetIds.includes(item.id))
                .map((item) => ({
                  value: item.id,
                  label: item.name || item.id,
                }))
            "
          />
          <a-button
            type="primary"
            :loading="submitLoading"
            :disabled="!assetIds.length"
            @click="handleAddAssets"
          >
            {{ $t("console.addSelected") }}
          </a-button>
          <a-button @click="handleUpload" type="primary" ghost>
            <template #icon><UploadOutlined /></template>
            {{ $t("console.upload") }}
          </a-button>
        </div>
        <a-list
          :data-source="assetPageData"
          :aria-busy="loading"
          :pagination="false"
          size="small"
          class="asset-list"
        >
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #avatar>
                  <a-avatar shape="square"
                    ><FileTextOutlined
                      :style="{
                        color: 'var(--color-primary-second)',
                        fontSize: '16px',
                      }"
                  /></a-avatar>
                </template>
                <template #title>
                  {{
                    assetList.find((asset) => asset.id === item)?.name || item
                  }}
                </template>
                <template #description>{{ item }}</template>
              </a-list-item-meta>
              <AssetStatus
                :value="assetList.find((asset) => asset.id === item)?.materialization || 'unknown'"
                :expired="assetList.find((asset) => asset.id === item)?.progressExpired"
              />
              <a-tag v-if="drawerData.asset_ids.includes(item)" :bordered="false" color="success">
                {{ $t("console.inPool") }}
              </a-tag>
            </a-list-item>
          </template>
        </a-list>
      </a-tab-pane>
      <a-tab-pane key="metadata" :tab="$t('console.metadata')">
        <JsonPretty
          v-if="Object.keys(drawerData.metadata || {}).length"
          :data="drawerData.metadata"
          :theme="themeStore.theme === 'dark' ? 'dark' : 'light'"
        />
        <a-empty v-else />
      </a-tab-pane>
    </a-tabs>
    <UploadDialog
      v-if="uploadDialog"
      :library-data="libraryData"
      :pool-id="drawerData.id"
      @close="handleUploadClose"
      @created="handleUploaded"
    />
    <template #footer>
      <div class="drawer-footer">
        <a-pagination
          v-if="activeKey === 'assets' && poolAssetIds.length > 10"
          v-model:current="assetPage"
          v-model:pageSize="assetPageSize"
          :total="poolAssetIds.length"
          :show-total="(total) => $t('console.totalRecords', { count: total })"
          :page-size-options="['10', '20', '50', '100']"
          showSizeChanger
          size="small"
        />
        <span class="footer-hint">{{ $t("console.poolHint") }}</span>
      </div>
    </template>
  </a-drawer>
</template>
<script lang="ts" setup name="DetailDrawer">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import {
  ApartmentOutlined,
  FileTextOutlined,
  SearchOutlined,
  UploadOutlined,
} from "@ant-design/icons-vue";
import {
  requestAssetPoolAssetsCreate,
  requestAssetPoolSourcesUpdate,
} from "@/api/console";
import type { AssetPool, IngestResult, Library } from "@/api/console/type";
import { themeAppStore } from "@/store/theme";
import JsonPretty from "vue-json-pretty";
import "vue-json-pretty/lib/styles.css";
import SourceBinding from "../../sources/components/SourceBinding.vue";
import StatusTag from "../../../components/StatusTag.vue";
import UploadDialog from "../../assets/components/UploadDialog.vue";
import { getAssetProgress, syncAssetProgress } from "../../assets/AssetUtils";
import AssetStatus from "../../assets/components/AssetStatus.vue";
import FormTooltip from "@/components/FormTooltip.vue";
import { customNotification } from "@/utils/notification";
const props = defineProps<{ drawerData: AssetPool; libraryData: Library }>();
const emit = defineEmits<{ close: []; search: [] }>();
const handleClose = () => emit("close");
const handleRetrieve = () =>
  router.push({
    path: "/retrieve",
    query: { pool: props.drawerData.id },
  });
const handleUpload = () => {
  uploadDialog.value = true;
};
const handleSearch = () => emit("search");
const handleUploadClose = () => {
  uploadDialog.value = false;
};
const router = useRouter();
const { t } = useI18n();
const themeStore = themeAppStore();
const drawerVisible = ref(true);
const activeKey = ref("sources");
const submitLoading = ref(false);
const uploadDialog = ref(false);
const loading = ref(true);
const progress = getAssetProgress(props.libraryData.name);
const assetList = computed(() => progress.rows);
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
let inFlight: Promise<void> | undefined;
const queryAssetList = (showLoading = false): Promise<void> => {
  if (!inFlight) {
    if (showLoading) {
      loading.value = true;
      progress.resume();
    }
    inFlight = (async () => {
      try {
        await syncAssetProgress(
          props.libraryData.name,
          progress,
          () => {
            const message = t("console.incompleteAssetList");
            customNotification("error", message, undefined);
            return new Error(message);
          },
          () => { if (!disposed) emit("search"); },
          () => !disposed,
          showLoading,
        );
      } finally {
        loading.value = false;
        if (!disposed && progress.expire())
          customNotification("warning", t("console.processing"), t("console.pollExpired"));
      }
    })().finally(() => { inFlight = undefined; });
  }
  return inFlight;
};
const poll = async () => {
  try {
    if (progress.trackedIds.length) await queryAssetList();
  } catch (error) {
    console.error(error);
  } finally {
    if (!disposed) timer = setTimeout(poll, 3000);
  }
};
onMounted(async () => {
  try {
    await queryAssetList(true);
  } catch (error) {
    console.error(error);
  } finally {
    if (!disposed) timer = setTimeout(poll, 3000);
  }
});
onUnmounted(() => {
  disposed = true;
  clearTimeout(timer);
});
const sourceIds = ref(
  props.drawerData.source_statuses.map((item) => item.source_id),
);
const assetIds = ref<string[]>([]);
const assetPage = ref(1);
const assetPageSize = ref(10);
const poolAssetIds = computed(() => [...new Set([
  ...assetList.value
    .filter((asset) => asset.asset_pool_ids.includes(props.drawerData.id))
    .map((asset) => asset.id),
  ...props.drawerData.asset_ids,
])]);
const assetPageData = computed(() =>
  poolAssetIds.value.slice(
    (assetPage.value - 1) * assetPageSize.value,
    assetPage.value * assetPageSize.value,
  ),
);
const sourceList = computed(() =>
  props.libraryData.sources.filter((item) => item.type !== "object"),
);
const handleSaveSources = async () => {
  submitLoading.value = true;
  try {
    await requestAssetPoolSourcesUpdate(
      props.libraryData.name,
      props.drawerData.id,
      { sources: sourceIds.value },
    );
    emit("search");
  } finally {
    submitLoading.value = false;
  }
};
const handleAddAssets = async () => {
  submitLoading.value = true;
  try {
    await requestAssetPoolAssetsCreate(
      props.libraryData.name,
      props.drawerData.id,
      { asset_ids: assetIds.value },
    );
    assetIds.value = [];
    emit("search");
  } finally {
    submitLoading.value = false;
  }
};
const handleUploaded = async (result: IngestResult) => {
  progress.accept(result);
  activeKey.value = "assets";
  assetPage.value = 1;
  await queryAssetList();
};
watch(assetPageSize, () => {
  assetPage.value = 1;
});
watch(
  () => props.drawerData.id,
  () => {
    assetPage.value = 1;
  },
);
watch(
  () => poolAssetIds.value.length,
  (total) => {
    assetPage.value = Math.min(
      assetPage.value,
      Math.max(1, Math.ceil(total / assetPageSize.value)),
    );
  },
);
</script>
<style scoped lang="less">
.detail-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin: 4px 0 24px;
  > div:nth-child(2) {
    flex: 1;
  }
}
.pool-icon {
  width: 48px;
  height: 48px;
  background: color-mix(in srgb, var(--color-purple) 10%, transparent);
  color: var(--color-purple);
  display: grid;
  place-items: center;
  border-radius: 10px;
  font-size: 25px;
}
.pool-id {
  font-family: monospace;
  color: var(--font-info-color);
  font-size: 12px;
  margin-bottom: 8px;
}
.stats-wrap {
  padding: 20px;
  border: 1px solid var(--border-main-color);
  border-radius: 8px;
  background: var(--bg-card-color);
  margin-bottom: 20px;
  :deep(.intel-statistic-content) {
    font-size: 24px;
  }
}
.section-hint,
.footer-hint {
  color: var(--font-info-color);
  font-size: 12px;
  line-height: 1.7;
}
.section-hint {
  margin-bottom: 18px;
}
.edit-section {
  border-top: 1px solid var(--border-main-color);
  margin-top: 24px;
  padding-top: 20px;
  h4 {
    color: var(--font-main-color);
  }
  .full-width {
    width: 100%;
    margin-bottom: 16px;
  }
}
.asset-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 16px 0;
  flex-wrap: wrap;
  .intel-select {
    flex: 1;
    min-width: 200px;
  }
}
.asset-list {
  :deep(.intel-list-item-meta) {
    display: flex;
    align-items: center;
  }
  :deep(.intel-list-item-meta-title) {
    margin-top: 0;
    margin-bottom: 4px;
  }
}
.drawer-footer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  :deep(.intel-pagination) {
    margin: 0;
  }
}
</style>
