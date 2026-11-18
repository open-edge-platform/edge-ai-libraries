<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div v-if="libraryData" class="canvas-container">
    <a-card :bordered="false" class="canvas-card">
      <div class="header-wrap">
        <div class="title-wrap">
          <NodeIndexOutlined />
          <button
            type="button"
            class="library-title"
            :title="$t('console.details')"
            @click="handleLibraryDetails"
          >
            {{ libraryData.name }}
            <EyeOutlined />
          </button>
          <a-tag
            v-for="item in resourceCategoryList"
            :key="item.kind"
            :bordered="false"
            class="resource-count"
            :data-kind="item.kind"
            :style="{ '--resource-color': item.color }"
          >
            <component :is="item.icon" />
            <span>{{ $t(`console.${item.label}`) }}</span>
            <strong>{{ resourceCounts[item.kind] }}</strong>
          </a-tag>
        </div>
        <div class="resource-actions">
          <a-button
            v-for="item in resourceCategoryList"
            :key="item.kind"
            :type="item.kind === 'asset' ? 'primary' : 'default'"
            class="resource-action"
            size="small"
            :class="{ 'primary-action': item.kind === 'asset' }"
            :style="{ '--resource-color': item.color }"
            @click="handleCreate(item.kind)"
          >
            <template #icon><component :is="item.createIcon" /></template>
            {{ $t(`console.${item.createLabel}`) }}
          </a-button>
        </div>
      </div>
      <div class="board-content" :aria-busy="loading">
        <CanvasBoard
          v-if="!loading"
          ref="boardRef"
          :library-data="libraryData"
          :node-list="nodeList"
          :edge-list="edgeList"
          :loading="submitLoading"
          :selection="{ key: selectedKey, edge: selectedEdge }"
          @connect="handleConnect"
          @select="handleSelect"
          @select-edge="handleSelectEdge"
          @files="handleDroppedFiles"
          @create="handleCreate"
          @deselect="handleDeselect"
          @detach="handleDetach()"
          @remove-node="handleRemoveNode"
        />
      </div>
    </a-card>
    <CanvasDetails
      :open="detailsVisible"
      :library-data="libraryData"
      :node="selectedNode"
      :edge="selectedEdge"
      :node-list="nodeList"
      :assets="assetList"
      :submit-loading="submitLoading"
      @close="handleDeselect"
      @connect="handleConnect"
      @add-assets="handleAddAssets"
      @detach="handleDetach"
      @select="handleSelect"
      @search="handleSearch"
      @manage="handleManagePool"
      @upload="handleUpload"
      @retrieve="handleRetrieve"
      @remove-node="handleRemoveNode"
      @delete-asset="handleDeleteAsset"
      @delete-pool="handleDeletePool"
      @delete-source="handleDeleteSource"
    />
    <CreatePoolDialog
      v-if="createPool"
      :library-data="libraryData"
      :initial-sources="
        creationTarget?.kind === 'source' &&
        creationTarget.resourceType !== 'object'
          ? [creationTarget.id]
          : []
      "
      @close="handleCreatePoolClose"
      @search="handleSearch"
      @created="handlePoolCreated"
    />
    <CreateSourceDialog
      v-if="createSource"
      :library-data="libraryData"
      @close="handleCreateSourceClose"
      @search="handleSearch"
      @created="handleSourceCreated"
    />
    <UploadDialog
      v-if="uploadDialog"
      :library-data="libraryData"
      :pool-id="uploadPool"
      :files="uploadFiles"
      @close="handleUploadClose"
      @created="handleUploaded"
    />
  </div>
</template>
<script lang="ts" setup name="ConsoleCanvas">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { Modal } from "ant-design-vue";
import { EyeOutlined, NodeIndexOutlined } from "@ant-design/icons-vue";
import {
  requestAssetDelete,
  requestAssetPoolAssetDelete,
  requestAssetPoolAssetsCreate,
  requestAssetPoolDelete,
  requestAssetPoolSourcesUpdate,
  requestSourceDelete,
} from "@/api/console";
import type { IngestResult, Source } from "@/api/console/type";
import { customNotification } from "@/utils/notification";
import type { ConsolePageProps } from "../../types/console";
import type { CanvasEdge, CanvasNode, NodeKind, Position } from "./Type";
import {
  buildCanvasEdges,
  buildCanvasNodes,
  getSourceDisplayStatus,
} from "./ResourceModel";
import { resourceCategoryList } from "./ResourcePresentation";
import CanvasBoard from "./components/CanvasBoard.vue";
import CanvasDetails from "./components/CanvasDetails.vue";
import CreatePoolDialog from "../pools/components/CreateDialog.vue";
import CreateSourceDialog from "../sources/components/CreateDialog.vue";
import UploadDialog from "../assets/components/UploadDialog.vue";
import {
  getAssetProgress,
  readDroppedFiles,
  syncAssetProgress,
} from "../assets/AssetUtils";
import type { StagedFile } from "../assets/AssetUtils";
import { isAssetDeletionBlocked } from "../assets/AssetProgress";
const props = defineProps<ConsolePageProps>();
const emit = defineEmits<{ refresh: [] }>();
const handleSearch = () => emit("refresh");
const handleCreatePoolClose = () => {
  createPool.value = false;
};
const handleCreateSourceClose = () => {
  createSource.value = false;
};
const handleUploadClose = () => {
  uploadDialog.value = false;
};
const handleManagePool = (id: string) =>
  router.push({ path: "/pools", query: { pool: id } });
const handleRetrieve = (pool?: string) =>
  router.push({ path: "/retrieve", query: pool ? { pool } : {} });
const { t } = useI18n();
const router = useRouter();
const boardRef = ref<InstanceType<typeof CanvasBoard>>();
const loading = ref(true);
const submitLoading = ref(false);
const createPool = ref(false);
const createSource = ref(false);
const uploadDialog = ref(false);
const uploadPool = ref<string>();
const uploadFiles = ref<StagedFile[]>([]);
const progress = getAssetProgress(props.libraryData!.name);
const assetList = computed(() => progress.rows);
const trackedIds = computed(() => progress.trackedIds);
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
          props.libraryData!.name,
          progress,
          () => {
            const message = t("console.incompleteAssetList");
            customNotification("error", message, undefined);
            return new Error(message);
          },
          () => {
            if (!disposed) emit("refresh");
          },
          () => !disposed,
          showLoading,
        );
      } finally {
        loading.value = false;
        if (!disposed && progress.expire())
          customNotification(
            "warning",
            t("console.processing"),
            t("console.pollExpired"),
          );
      }
    })().finally(() => {
      inFlight = undefined;
    });
  }
  return inFlight;
};
const poll = async () => {
  try {
    if (trackedIds.value.length) await queryAssetList();
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
const resourceCounts = computed(() => ({
  asset: assetList.value.length,
  pool: props.libraryData?.asset_pools.length || 0,
  source: props.libraryData?.sources.length || 0,
}));
const selectedKey = ref("");
const selectedEdge = ref<CanvasEdge>();
const detailsVisible = ref(false);
const creationPosition = ref<Position>();
const creationTarget = ref<CanvasNode>();
const pendingSelection = ref("");
const nodeList = computed<CanvasNode[]>(() =>
  props.libraryData
    ? buildCanvasNodes(props.libraryData, assetList.value, trackedIds.value)
    : [],
);
const edgeList = computed<CanvasEdge[]>(() =>
  props.libraryData ? buildCanvasEdges(props.libraryData) : [],
);
const selectedNode = computed(() =>
  nodeList.value.find((node) => node.key === selectedKey.value),
);
const selectedAsset = computed(() =>
  assetList.value.find((item) => `asset:${item.id}` === selectedKey.value),
);
const selectedPool = computed(() =>
  props.libraryData?.asset_pools.find(
    (item) => `pool:${item.id}` === selectedKey.value,
  ),
);
const selectedSource = computed(() =>
  props.libraryData?.sources.find(
    (item) => `source:${item.id}` === selectedKey.value,
  ),
);
const handleSelect = (key: string) => {
  selectedKey.value = key;
  selectedEdge.value = undefined;
  detailsVisible.value = true;
};
const handleSelectEdge = (edge: CanvasEdge) => {
  selectedEdge.value = edge;
  selectedKey.value = "";
  detailsVisible.value = true;
};
const handleRemoveNode = (key: string) => {
  if (key.startsWith("asset:")) {
    const assetId = key.slice("asset:".length);
    const pools = props.libraryData?.asset_pools.filter((pool) =>
      pool.asset_ids.includes(assetId),
    );
    if (pools?.length) {
      Modal.warning({
        title: t("console.removeCanvas"),
        content: t("console.removeCanvasLinkedAsset", {
          pools: pools.map((pool) => pool.name).join(", "),
        }),
        okText: t("common.confirm"),
      });
      return;
    }
  }
  boardRef.value?.removeNode(key);
  if (selectedKey.value === key) handleDeselect();
};
const handleDeselect = () => {
  selectedKey.value = "";
  selectedEdge.value = undefined;
  detailsVisible.value = false;
};
const handleLibraryDetails = () => {
  handleDeselect();
  detailsVisible.value = true;
};
const handleConnect = async (from: string, to: string) => {
  if (submitLoading.value) return;
  const a = nodeList.value.find((node) => node.key === from);
  const b = nodeList.value.find((node) => node.key === to);
  const pool = [a, b].find((node) => node?.kind === "pool");
  const item = [a, b].find((node) => node && node !== pool);
  if (!pool || !item || item.kind === "pool") {
    customNotification("warning", t("common.prompt"), t("console.invalidLink"));
    return;
  }
  if (
    item.kind === "asset" &&
    assetList.value.find((asset) => asset.id === item.id)?.pending
  ) {
    customNotification(
      "info",
      t("common.prompt"),
      t("console.assetPendingHint"),
    );
    return;
  }
  const data = props.libraryData!.asset_pools.find(
    (value) => value.id === pool.id,
  )!;
  if (
    (item.kind === "asset" && data.asset_ids.includes(item.id)) ||
    (item.kind === "source" &&
      data.source_statuses.some((status) => status.source_id === item.id))
  ) {
    customNotification("info", t("common.prompt"), t("console.existingLink"));
    return;
  }
  if (
    (item.kind === "source" &&
      props.libraryData!.sources.find((source) => source.id === item.id)
        ?.type === "object") ||
    item.content
  ) {
    customNotification("info", t("common.prompt"), t("console.contentLink"));
    return;
  }
  submitLoading.value = true;
  try {
    if (item.kind === "asset")
      await requestAssetPoolAssetsCreate(props.libraryData!.name, pool.id, {
        asset_ids: [item.id],
      });
    else
      await requestAssetPoolSourcesUpdate(props.libraryData!.name, pool.id, {
        sources: [
          ...data.source_statuses.map((status) => status.source_id),
          item.id,
        ],
      });
    boardRef.value?.placeNodes([pool.key, item.key]);
    emit("refresh");
    await queryAssetList();
  } finally {
    submitLoading.value = false;
  }
};
const handleAddAssets = async (poolId: string, assetIds: string[]) => {
  if (submitLoading.value || !assetIds.length) return;
  submitLoading.value = true;
  try {
    await requestAssetPoolAssetsCreate(props.libraryData!.name, poolId, {
      asset_ids: assetIds,
    });
    boardRef.value?.placeNodes([
      `pool:${poolId}`,
      ...assetIds.map((id) => `asset:${id}`),
    ]);
    emit("refresh");
    await queryAssetList();
  } finally {
    submitLoading.value = false;
  }
};
const detachBlocked = (edge: CanvasEdge) => {
  if (edge.from.startsWith("asset:")) {
    const asset = assetList.value.find(
      (item) => `asset:${item.id}` === edge.from,
    );
    return (
      !asset || isAssetDeletionBlocked(asset, props.libraryData!.asset_pools)
    );
  }
  const pool = props.libraryData!.asset_pools.find(
    (item) => `pool:${item.id}` === edge.from,
  );
  const source = props.libraryData!.sources.find(
    (item) => `source:${item.id}` === edge.to,
  );
  return (
    pool?.display_status === "indexing" ||
    (!!source &&
      getSourceDisplayStatus(props.libraryData!, source) === "indexing")
  );
};
const handleDetach = (edge = selectedEdge.value) => {
  if (!edge || submitLoading.value) return;
  if (
    edge.content ||
    edge.to === `source:${props.libraryData!.default_content_source_id}`
  ) {
    customNotification("info", t("common.prompt"), t("console.contentLink"));
    return;
  }
  if (detachBlocked(edge)) return;
  if (edge.from.startsWith("asset:")) {
    const assetId = edge.from.slice("asset:".length);
    const poolId = edge.to.slice("pool:".length);
    Modal.confirm({
      title: t("console.removeOneFromPool"),
      content: t("console.removePoolAssetsConfirm", { count: 1 }),
      okType: "danger",
      okText: t("common.confirm"),
      cancelText: t("common.cancel"),
      async onOk() {
        if (detachBlocked(edge)) return;
        submitLoading.value = true;
        try {
          await requestAssetPoolAssetDelete(
            props.libraryData!.name,
            poolId,
            assetId,
          );
          if (
            selectedEdge.value?.from === edge.from &&
            selectedEdge.value?.to === edge.to
          )
            handleDeselect();
          emit("refresh");
          await queryAssetList();
        } finally {
          submitLoading.value = false;
        }
      },
    });
    return;
  }
  const pool = props.libraryData!.asset_pools.find(
    (item) => `pool:${item.id}` === edge.from,
  )!;
  const sources = pool.source_statuses
    .map((status) => status.source_id)
    .filter((id) => `source:${id}` !== edge.to);
  if (!sources.length) {
    customNotification(
      "warning",
      t("common.prompt"),
      t("console.sourceRequired"),
    );
    return;
  }
  Modal.confirm({
    title: t("console.detach"),
    content: t("console.detachSource"),
    okText: t("common.confirm"),
    cancelText: t("common.cancel"),
    async onOk() {
      if (detachBlocked(edge)) return;
      submitLoading.value = true;
      try {
        await requestAssetPoolSourcesUpdate(props.libraryData!.name, pool.id, {
          sources,
        });
        if (
          selectedEdge.value?.from === edge.from &&
          selectedEdge.value?.to === edge.to
        )
          handleDeselect();
        emit("refresh");
      } finally {
        submitLoading.value = false;
      }
    },
  });
};
const handleUpload = (pool?: string, position?: Position) => {
  uploadPool.value = pool;
  creationPosition.value = position;
  uploadFiles.value = [];
  uploadDialog.value = true;
};
const handleCreate = (
  kind: NodeKind,
  position?: Position,
  target?: CanvasNode,
) => {
  creationPosition.value = position;
  creationTarget.value = target;
  if (kind === "asset")
    handleUpload(target?.kind === "pool" ? target.id : undefined, position);
  else if (kind === "pool") createPool.value = true;
  else createSource.value = true;
};
const handlePoolCreated = async (id: string) => {
  const target = creationTarget.value;
  boardRef.value?.placeNodes([`pool:${id}`], creationPosition.value);
  pendingSelection.value = `pool:${id}`;
  if (target?.kind === "asset") {
    await requestAssetPoolAssetsCreate(props.libraryData!.name, id, {
      asset_ids: [target.id],
    });
    emit("refresh");
  }
};
const handleSourceCreated = async (id: string, source: Source) => {
  const target = creationTarget.value;
  boardRef.value?.placeNodes([`source:${id}`], creationPosition.value);
  pendingSelection.value = `source:${id}`;
  if (target?.kind === "pool") {
    if (source.type === "object") {
      customNotification("info", t("common.prompt"), t("console.contentHint"));
      return;
    }
    const pool = props.libraryData!.asset_pools.find(
      (item) => item.id === target.id,
    )!;
    await requestAssetPoolSourcesUpdate(props.libraryData!.name, pool.id, {
      sources: [
        ...pool.source_statuses.map((binding) => binding.source_id),
        id,
      ],
    });
    emit("refresh");
  }
};
const handleDroppedFiles = async (
  data: DataTransfer,
  target?: CanvasNode,
  position?: Position,
) => {
  creationPosition.value = position;
  try {
    uploadFiles.value = await readDroppedFiles(data);
    uploadPool.value = target?.kind === "pool" ? target.id : undefined;
    uploadDialog.value = true;
  } catch (error) {
    customNotification(
      "error",
      t("common.error"),
      error instanceof Error ? error.message : String(error),
    );
  }
};
const handleUploaded = async (result: IngestResult) => {
  const ids = result.asset_ids;
  progress.accept(result);
  boardRef.value?.placeNodes(
    ids.map((id) => `asset:${id}`),
    creationPosition.value,
  );
  if (ids.length === 1) pendingSelection.value = `asset:${ids[0]}`;
  await queryAssetList();
  emit("refresh");
};
const handleDeleteAsset = () => {
  const asset = selectedAsset.value;
  if (!asset || isAssetDeletionBlocked(asset, props.libraryData!.asset_pools))
    return;
  const id = asset.id;
  Modal.confirm({
    title: t("common.delete"),
    content: t("console.deleteAssets", { count: 1 }),
    okType: "danger",
    async onOk() {
      const current = assetList.value.find((item) => item.id === id);
      if (
        !current ||
        isAssetDeletionBlocked(current, props.libraryData!.asset_pools)
      )
        return;
      await requestAssetDelete(props.libraryData!.name, {
        asset_ids: [id],
      });
      boardRef.value?.removeNode(`asset:${id}`);
      if (selectedKey.value === `asset:${id}`) handleDeselect();
      progress.remove([id]);
      await queryAssetList();
      emit("refresh");
    },
  });
};
const handleDeletePool = () => {
  const pool = selectedPool.value;
  if (!pool || pool.display_status === "indexing") return;
  const id = pool.id;
  Modal.confirm({
    title: t("common.delete"),
    content: t("console.deletePool", { name: pool.name }),
    okType: "danger",
    async onOk() {
      const current = props.libraryData!.asset_pools.find(
        (item) => item.id === id,
      );
      if (!current || current.display_status === "indexing") return;
      await requestAssetPoolDelete(props.libraryData!.name, id);
      boardRef.value?.removeNode(`pool:${id}`);
      if (selectedKey.value === `pool:${id}`) handleDeselect();
      emit("refresh");
    },
  });
};
const handleDeleteSource = () => {
  const source = selectedSource.value;
  if (
    !source ||
    getSourceDisplayStatus(props.libraryData!, source) === "indexing"
  )
    return;
  const id = source.id;
  Modal.confirm({
    title: t("common.delete"),
    content: t("console.deleteSource", { name: source.name }),
    okType: "danger",
    async onOk() {
      const current = props.libraryData!.sources.find((item) => item.id === id);
      if (
        !current ||
        getSourceDisplayStatus(props.libraryData!, current) === "indexing"
      )
        return;
      await requestSourceDelete(props.libraryData!.name, id);
      boardRef.value?.removeNode(`source:${id}`);
      if (selectedKey.value === `source:${id}`) handleDeselect();
      emit("refresh");
    },
  });
};
watch(nodeList, (nodes) => {
  if (
    pendingSelection.value &&
    nodes.some((node) => node.key === pendingSelection.value)
  ) {
    handleSelect(pendingSelection.value);
    pendingSelection.value = "";
  } else if (
    selectedKey.value &&
    !nodes.some((node) => node.key === selectedKey.value)
  ) {
    handleDeselect();
  }
});
watch(edgeList, (edges) => {
  if (selectedEdge.value) {
    selectedEdge.value = edges.find(
      (edge) =>
        edge.from === selectedEdge.value?.from &&
        edge.to === selectedEdge.value?.to,
    );
    if (!selectedEdge.value) detailsVisible.value = false;
  }
});
</script>
<style scoped lang="less">
.canvas-card,
.board-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.canvas-card {
  background: var(--bg-content-color);
  border: 1px solid var(--border-main-color);
  border-radius: 8px;
  overflow: hidden;
  :deep(.intel-card-body) {
    padding: 0;
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }
}
.header-wrap {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border-main-color);
  flex-wrap: wrap;
}
.title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--font-main-color);
  > .anticon {
    color: var(--color-primary-second);
    font-size: 19px;
  }
  > span {
    font-weight: 500;
  }
  :deep(.intel-tag) {
    margin: 0;
  }
}
.resource-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  flex-shrink: 0;
  gap: 8px;
  max-width: 100%;
  :deep(.intel-btn + .intel-btn) {
    margin-left: 0;
  }
}
.resource-count {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
  background: color-mix(
    in srgb,
    var(--resource-color) 7%,
    var(--bg-content-color)
  );
  color: var(--font-text-color);
  > .anticon {
    color: var(--resource-color);
    font-size: 13px;
  }
  strong {
    color: var(--resource-color);
    font-weight: 600;
  }
}
.resource-action {
  white-space: nowrap;
  &:not(.primary-action) :deep(.anticon) {
    color: var(--resource-color);
  }
}
.library-title {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--font-main-color);
  font-weight: 500;
  cursor: pointer;
  .anticon {
    margin-left: 4px;
    color: var(--font-info-color);
  }
}
</style>
