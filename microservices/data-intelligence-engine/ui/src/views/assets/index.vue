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
      @upload="handleUpload"
      @view="handleView"
      @search="handleSearch"
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
import { getAssetList } from "@/api/console";
import type { Asset } from "@/api/console/type";
import { customNotification } from "@/utils/notification";
import type { ConsolePageProps } from "../../types/console";
import Table from "./components/Table.vue";
import UploadDialog from "./components/UploadDialog.vue";
import DetailDrawer from "./components/DetailDrawer.vue";
import { collectAssets } from "./AssetList";
const props = defineProps<ConsolePageProps>();
const emit = defineEmits<{ refresh: [] }>();
const route = useRoute();
const { t } = useI18n();
const loading = ref(false);
const tableData = ref<Asset[]>([]);
const trackedAssets = ref<string[]>([]);
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
let timer: ReturnType<typeof setTimeout>;
let disposed = false;
let watchStarted = 0;
const queryAssetList = async (showLoading = false) => {
  const assets = await collectAssets(
    (page) => getAssetList(props.libraryData!.name, {
      page_num: page,
      page_size: 500,
    }, showLoading && page === 1),
    () => {
      const message = t("console.incompleteAssetList");
      customNotification("error", message, undefined);
      return new Error(message);
    },
  );
  if (disposed) return;
  tableData.value = assets;
  trackedAssets.value = trackedAssets.value.filter((id) => {
    const asset = assets.find((item) => item.id === id);
    return (
      !asset ||
      (asset.materialization !== null && asset.materialization !== "ready")
    );
  });
  for (const asset of assets) {
    if (
      asset.materialization &&
      asset.materialization !== "ready" &&
      !trackedAssets.value.includes(asset.id)
    ) {
      trackedAssets.value.push(asset.id);
    }
  }
  if (trackedAssets.value.length && !watchStarted) watchStarted = Date.now();
};
const handleSearch = async () => {
  loading.value = true;
  try {
    await queryAssetList(true);
    emit("refresh");
  } finally {
    loading.value = false;
  }
};
const handleView = (id: string) => {
  selectedId.value = id;
};
const handleUploaded = async (ids: string[]) => {
  trackedAssets.value.push(...ids);
  watchStarted = Date.now();
  await handleSearch();
};
const queryIngestStatus = async () => {
  if (trackedAssets.value.length && !loading.value) {
    try {
      await queryAssetList();
      emit("refresh");
    } catch (error) {
      console.error(error);
    }
    if (Date.now() - watchStarted > 600000) {
      trackedAssets.value = [];
      customNotification(
        "warning",
        t("console.processing"),
        t("console.pollExpired"),
      );
    }
  }
  if (!disposed) timer = setTimeout(queryIngestStatus, 3000);
};
onMounted(async () => {
  await handleSearch();
  if (!disposed) timer = setTimeout(queryIngestStatus, 3000);
});
onUnmounted(() => {
  disposed = true;
  clearTimeout(timer);
});
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
