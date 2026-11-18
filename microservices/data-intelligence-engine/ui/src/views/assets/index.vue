<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div v-if="libraryData" class="asset-container">
    <div class="library-info">
      <div class="library-icon"><DatabaseOutlined /></div>
      <div>
        <strong>{{ libraryData.name }}</strong>
        <p>{{ libraryData.description || $t("console.assetsHint") }}</p>
      </div>
      <div class="library-count">
        <strong>{{ libraryData.asset_count }}</strong>
        <span>{{ $t("console.assets") }}</span>
      </div>
      <div class="library-count">
        <strong>{{ libraryData.chunk_count }}</strong>
        <span>{{ $t("console.chunks") }}</span>
      </div>
    </div>
    <a-alert
      v-if="trackedAssets.length"
      type="info"
      showIcon
      :message="$t('console.accepted', { count: trackedAssets.length })"
      class="progress-wrap"
    />
    <Table
      :table-data="tableData"
      :pool-data="libraryData.asset_pools"
      :library-name="libraryData.name"
      :upload-version="uploadVersion"
      @upload="handleUpload"
      @view="handleView"
      @search="handleSearch"
      @deleted="removeAssets"
    />
    <UploadDialog
      v-if="uploadDialog"
      :library-data="libraryData"
      :pool-id="
        typeof route.query.pool === 'string' ? route.query.pool : undefined
      "
      @close="handleUploadClose"
      @created="handleUploaded"
    />
    <DetailDrawer
      v-if="detailDrawer"
      :drawer-data="detailDrawer"
      :library-data="libraryData"
      @close="handleDetailClose"
    />
  </div>
</template>
<script lang="ts" setup name="ConsoleAssets">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { DatabaseOutlined } from "@ant-design/icons-vue";
import type { IngestResult } from "@/api/console/type";
import { customNotification } from "@/utils/notification";
import type { ConsolePageProps } from "../../types/console";
import Table from "./components/Table.vue";
import UploadDialog from "./components/UploadDialog.vue";
import DetailDrawer from "./components/DetailDrawer.vue";
import { getAssetProgress, syncAssetProgress } from "./AssetUtils";
const props = defineProps<ConsolePageProps>();
const emit = defineEmits<{ refresh: [] }>();
const route = useRoute();
const { t } = useI18n();
const progress = getAssetProgress(props.libraryData!.name);
const tableData = computed(() => progress.rows);
const trackedAssets = computed(() => progress.trackedIds);
const removeAssets = (ids: string[]) => progress.remove(ids);
const uploadVersion = ref(0);
const uploadDialog = ref(route.query.upload === "1");
const selectedId = ref("");
const detailDrawer = computed(() => tableData.value.find((asset) => asset.id === selectedId.value));
const handleUpload = () => {
  uploadDialog.value = true;
};
const handleUploadClose = () => {
  uploadDialog.value = false;
};
const handleDetailClose = () => {
  selectedId.value = "";
};
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
let inFlight: Promise<void> | undefined;
const queryAssetList = (showLoading = false): Promise<void> => {
  if (!inFlight) {
    if (showLoading) progress.resume();
    inFlight = (async () => {
      try {
        await syncAssetProgress(
          props.libraryData!.name,
          progress,
          () => {
            const message = t("console.incompleteAssetList");
            customNotification("error", message, undefined);
            return new Error(message);
          },
          () => { if (!disposed) emit("refresh"); },
          () => !disposed,
          showLoading,
        );
      } finally {
        if (!disposed && progress.expire())
          customNotification("warning", t("console.processing"), t("console.pollExpired"));
      }
    })().finally(() => { inFlight = undefined; });
  }
  return inFlight;
};
const poll = async () => {
  try {
    if (trackedAssets.value.length) await queryAssetList();
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
const handleSearch = () => queryAssetList(true);
const handleView = (id: string) => {
  selectedId.value = id;
};
const handleUploaded = async (result: IngestResult) => {
  progress.accept(result);
  uploadVersion.value++;
  await queryAssetList();
};
</script>
<style scoped lang="less">
.library-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  flex-shrink: 0;
  background: var(--bg-content-color);
  border: 1px solid var(--border-main-color);
  border-radius: 8px;
  margin-bottom: 12px;
  > div:nth-child(2) {
    flex: 1;
    min-width: 0;
    strong {
      color: var(--font-main-color);
      font-size: 14px;
    }
    p {
      font-size: 12px;
      color: var(--font-info-color);
      margin: 2px 0 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
}
.library-icon {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: 6px;
  background: color-mix(in srgb, var(--color-primary-second) 10%, transparent);
  color: var(--color-primary-second);
  display: grid;
  place-items: center;
  font-size: 18px;
}
.library-count {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding-left: 16px;
  border-left: 1px solid var(--border-main-color);
  strong {
    font-size: 18px;
    font-weight: 500;
    color: var(--font-main-color);
  }
  span {
    font-size: 12px;
    color: var(--font-info-color);
  }
}
.progress-wrap {
  margin-bottom: 12px;
  flex-shrink: 0;
}
@media (max-width: 700px) {
  .library-info {
    flex-wrap: wrap;
  }
  .library-count {
    padding-left: 0;
    border-left: 0;
  }
}
</style>
