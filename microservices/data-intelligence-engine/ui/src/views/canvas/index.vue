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
          :library-id="libraryData.id"
          :node-list="nodeList"
          :edge-list="edgeList"
          :loading="submitLoading"
          :selected-key="selectedKey"
          :selected-edge="selectedEdge"
          @connect="handleConnect"
          @select="handleSelect"
          @select-edge="handleSelectEdge"
          @files="handleDroppedFiles"
          @create="handleCreate"
          @deselect="handleDeselect"
          @detach="handleDetach()"
        />
      </div>
    </a-card>
    <a-drawer
      :open="detailsVisible"
      :title="$t('console.details')"
      width="min(440px, 100vw)"
      :mask="false"
      class="canvas-inspector"
      @close="handleDeselect"
    >
      <template v-if="selectedNode">
        <div class="detail-title">
          <CanvasResource :node="selectedNode" />
          <a-typography-text copyable class="resource-id">{{
            selectedNode.id
          }}</a-typography-text>
        </div>
        <template v-if="selectedAsset">
          <a-descriptions :column="1" bordered size="small">
            <a-descriptions-item :label="$t('console.origin')">
              {{ selectedAsset.origin }}
            </a-descriptions-item>
            <a-descriptions-item :label="$t('console.kind')">
              {{
                $te(`console.${selectedAsset.kind}`)
                  ? $t(`console.${selectedAsset.kind}`)
                  : selectedAsset.kind
              }}
            </a-descriptions-item>
            <a-descriptions-item :label="$t('console.mediaType')">
              {{ selectedAsset.media_type || "—" }}
            </a-descriptions-item>
            <a-descriptions-item :label="$t('console.contentSource')">
              {{
                libraryData.sources.find(
                  (source) => source.id === selectedAsset?.content_source_id,
                )?.name ||
                selectedAsset.content_source_id ||
                "—"
              }}
            </a-descriptions-item>
            <a-descriptions-item :label="$t('console.pools')">
              <a-tag v-for="pool in selectedAssetPools" :key="pool.id">
                {{ pool.name }}
              </a-tag>
              <span v-if="!selectedAssetPools.length">{{
                $t("console.none")
              }}</span>
            </a-descriptions-item>
          </a-descriptions>
          <div v-if="availablePools.length" class="association-wrap">
            <h4>{{ $t("console.addToPool") }}</h4>
            <div class="association-controls">
              <a-select
                v-model:value="relatedPoolId"
                showSearch
                optionFilterProp="label"
                :placeholder="$t('console.pleaseSelect')"
                :options="
                  availablePools.map((pool) => ({
                    value: pool.id,
                    label: pool.name,
                  }))
                "
              />
              <a-button
                :loading="submitLoading"
                :disabled="!relatedPoolId"
                @click="handleConnect(selectedKey, `pool:${relatedPoolId}`)"
              >
                {{ $t("console.add") }}
              </a-button>
            </div>
          </div>
          <a-button
            danger
            class="detail-action"
            :disabled="selectedAsset.pending"
            :title="selectedAsset.pending ? $t('console.assetPendingHint') : undefined"
            @click="handleDeleteAsset"
          >
            {{ $t("common.delete") }}
          </a-button>
        </template>
        <template v-else-if="selectedPool">
          <a-row :gutter="16" class="stats-wrap">
            <a-col :span="8">
              <a-statistic
                :title="$t('console.assets')"
                :value="selectedPool.asset_ids.length"
              />
            </a-col>
            <a-col :span="8">
              <a-statistic
                :title="$t('console.sources')"
                :value="selectedPool.source_statuses.length"
              />
            </a-col>
            <a-col :span="8">
              <a-statistic
                :title="$t('console.revision')"
                :value="selectedPool.revision"
              />
            </a-col>
          </a-row>
          <SourceBinding
            v-for="binding in selectedPool.source_statuses"
            :key="binding.source_id"
            :library-data="libraryData"
            :pool="selectedPool"
            :binding="binding"
            removable
            @search="handleSearch"
            @detach="
              handleDetach({
                from: `pool:${selectedPool.id}`,
                to: `source:${binding.source_id}`,
              })
            "
          />
          <div v-if="availableSources.length" class="association-wrap">
            <h4>{{ $t("console.attachSource") }}</h4>
            <div class="association-controls">
              <a-select
                v-model:value="relatedSourceId"
                showSearch
                optionFilterProp="label"
                :placeholder="$t('console.pleaseSelect')"
                :options="
                  availableSources.map((source) => ({
                    value: source.id,
                    label: `${source.name} (${source.type})`,
                  }))
                "
              />
              <a-button
                :loading="submitLoading"
                :disabled="!relatedSourceId"
                @click="handleConnect(selectedKey, `source:${relatedSourceId}`)"
              >
                {{ $t("console.add") }}
              </a-button>
            </div>
          </div>
          <a-collapse ghost class="pool-information">
            <a-collapse-panel
              key="assets"
              :header="`${$t('console.poolAssets')} (${selectedPool.asset_ids.length})`"
            >
              <a-list :data-source="selectedPool.asset_ids" size="small">
                <template #renderItem="{ item }">
                  <a-list-item>
                    <a @click="handleSelect(`asset:${item}`)">
                      {{
                        assetList.find((asset) => asset.id === item)?.name ||
                        item
                      }}
                    </a>
                  </a-list-item>
                </template>
              </a-list>
            </a-collapse-panel>
            <a-collapse-panel key="metadata" :header="$t('console.metadata')">
              <JsonPretty
                :data="selectedPool.metadata"
                :theme="themeStore.theme === 'dark' ? 'dark' : 'light'"
              />
            </a-collapse-panel>
          </a-collapse>
          <div v-if="availableAssets.length" class="association-wrap">
            <h4>{{ $t("console.addAssets") }}</h4>
            <div class="association-controls">
              <a-select
                v-model:value="relatedAssetId"
                showSearch
                optionFilterProp="label"
                :placeholder="$t('console.pleaseSelect')"
                :options="
                  availableAssets.map((asset) => ({
                    value: asset.id,
                    label: asset.name || asset.id,
                  }))
                "
              />
              <a-button
                :loading="submitLoading"
                :disabled="!relatedAssetId"
                @click="handleConnect(`asset:${relatedAssetId}`, selectedKey)"
              >
                {{ $t("console.add") }}
              </a-button>
            </div>
          </div>
          <p class="section-hint">{{ $t("console.poolHint") }}</p>
          <a-space wrap class="detail-action">
            <a-button
              type="primary"
              ghost
              @click="handleManagePool(selectedPool.id)"
            >
              {{ $t("console.manage") }}
            </a-button>
            <a-button @click="handleUpload(selectedPool.id)">
              {{ $t("console.upload") }}
            </a-button>
            <a-button @click="handleRetrieve(selectedPool.id)">
              {{ $t("console.retrieve") }}
            </a-button>
            <a-button danger @click="handleDeletePool">
              {{ $t("common.delete") }}
            </a-button>
          </a-space>
        </template>
        <template v-else-if="selectedSource">
          <a-descriptions :column="1" bordered size="small">
            <a-descriptions-item :label="$t('console.type')">
              {{
                $te(`console.${selectedSource.type}Source`)
                  ? $t(`console.${selectedSource.type}Source`)
                  : selectedSource.type
              }}
            </a-descriptions-item>
            <a-descriptions-item :label="$t('console.database')">
              {{ selectedSource.database_id }}
            </a-descriptions-item>
            <a-descriptions-item :label="$t('console.collection')">
              {{ selectedSource.collection_name }}
            </a-descriptions-item>
            <a-descriptions-item :label="$t('console.status')">
              {{
                $t(
                  selectedSource.enabled
                    ? "console.enabled"
                    : "console.DISABLED",
                )
              }}
            </a-descriptions-item>
            <a-descriptions-item :label="$t('console.validation')">
              <StatusTag
                :value="
                  selectedSource.reconciled ? 'reconciled' : 'unreconciled'
                "
              />
            </a-descriptions-item>
            <a-descriptions-item
              v-if="selectedNode.content"
              :label="$t('console.role')"
            >
              {{ $t("console.defaultContent") }}
            </a-descriptions-item>
          </a-descriptions>
          <a-alert
            v-if="selectedSource.reconciliation_error"
            type="error"
            showIcon
            :message="selectedSource.reconciliation_error"
            class="detail-notice"
          />
          <div class="configuration-wrap">
            <h4>{{ $t("console.sourceConfiguration") }}</h4>
            <JsonPretty
              :data="selectedSource.operator_options"
              :theme="themeStore.theme === 'dark' ? 'dark' : 'light'"
            />
            <p class="section-hint">{{ $t("console.sourcesHint") }}</p>
          </div>
          <h4>{{ $t("console.inUseBy") }}</h4>
          <template v-if="selectedNode.content">
            <a-tag v-for="pool in libraryData.asset_pools" :key="pool.id">{{
              pool.name
            }}</a-tag>
            <p class="section-hint">{{ $t("console.contentLink") }}</p>
          </template>
          <template v-else>
            <div v-for="entry in selectedSourceBindings" :key="entry.pool.id">
              <h4>{{ entry.pool.name }}</h4>
              <SourceBinding
                :library-data="libraryData"
                :pool="entry.pool"
                :binding="entry.binding"
                removable
                @search="handleSearch"
                @detach="
                  handleDetach({
                    from: `pool:${entry.pool.id}`,
                    to: selectedKey,
                  })
                "
              />
            </div>
            <p v-if="!selectedSourceBindings.length" class="section-hint">
              {{ $t("console.none") }}
            </p>
            <div
              v-if="availablePools.length && selectedSource.type !== 'object'"
              class="association-wrap"
            >
              <h4>{{ $t("console.addToPool") }}</h4>
              <div class="association-controls">
                <a-select
                  v-model:value="relatedPoolId"
                  showSearch
                  optionFilterProp="label"
                  :placeholder="$t('console.pleaseSelect')"
                  :options="
                    availablePools.map((pool) => ({
                      value: pool.id,
                      label: pool.name,
                    }))
                  "
                />
                <a-button
                  :loading="submitLoading"
                  :disabled="!relatedPoolId"
                  @click="handleConnect(`pool:${relatedPoolId}`, selectedKey)"
                >
                  {{ $t("console.add") }}
                </a-button>
              </div>
            </div>
          </template>
          <a-button danger @click="handleDeleteSource">
            {{ $t("common.delete") }}
          </a-button>
        </template>
        <a-divider />
        <a-space wrap>
          <a-button @click="handleShowLinked">
            {{ $t("console.showLinked") }}
          </a-button>
          <a-button @click="handleRemoveNode">
            {{ $t("console.removeCanvas") }}
          </a-button>
        </a-space>
      </template>
      <template v-else-if="selectedEdge">
        <div class="link-summary">
          <span>
            {{ nodeList.find((node) => node.key === selectedEdge?.from)?.name }}
          </span>
          <ArrowRightOutlined />
          <span>
            {{ nodeList.find((node) => node.key === selectedEdge?.to)?.name }}
          </span>
        </div>
        <SourceBinding
          v-if="selectedEdgePool && selectedEdgeBinding"
          :library-data="libraryData"
          :pool="selectedEdgePool"
          :binding="selectedEdgeBinding"
          @search="handleSearch"
        />
        <a-alert
          v-if="selectedEdge.content"
          type="info"
          showIcon
          :message="$t('console.contentLink')"
        />
        <a-alert
          v-else-if="selectedEdge.from.startsWith('asset:')"
          type="info"
          showIcon
          :message="$t('console.assetLink')"
        />
        <template v-else>
          <p class="section-hint">{{ $t("console.detachHint") }}</p>
          <a-button danger :loading="submitLoading" @click="handleDetach()">
            {{ $t("console.detach") }}
          </a-button>
        </template>
      </template>
      <template v-else>
        <h3>{{ libraryData.name }}</h3>
        <a-descriptions :column="1" bordered size="small">
          <a-descriptions-item :label="$t('console.description')">{{
            libraryData.description || $t("console.noDescription")
          }}</a-descriptions-item>
          <a-descriptions-item :label="$t('console.assets')">{{
            libraryData.asset_count
          }}</a-descriptions-item>
          <a-descriptions-item :label="$t('console.documents')">{{
            libraryData.document_count
          }}</a-descriptions-item>
          <a-descriptions-item :label="$t('console.chunks')">{{
            libraryData.chunk_count
          }}</a-descriptions-item>
          <a-descriptions-item :label="$t('console.pools')">{{
            libraryData.asset_pools.length
          }}</a-descriptions-item>
          <a-descriptions-item :label="$t('console.sources')">{{
            libraryData.sources.length
          }}</a-descriptions-item>
          <a-descriptions-item :label="$t('console.contentDatabase')">{{
            libraryData.content_database || "—"
          }}</a-descriptions-item>
        </a-descriptions>
        <p class="section-hint detail-notice">
          {{ $t("console.canvasInteractionHint") }}
        </p>
        <a-button type="primary" @click="handleRetrieve()">{{
          $t("console.retrieve")
        }}</a-button>
      </template>
      <template #footer
        ><span class="section-hint">{{
          $t("console.canvasKeyboardHint")
        }}</span></template
      >
    </a-drawer>
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
import {
  ArrowRightOutlined,
  EyeOutlined,
  NodeIndexOutlined,
} from "@ant-design/icons-vue";
import {
  requestAssetDelete,
  requestAssetPoolAssetsCreate,
  requestAssetPoolDelete,
  requestAssetPoolSourcesUpdate,
  requestSourceDelete,
} from "@/api/console";
import type { IngestResult, Source } from "@/api/console/type";
import { customNotification } from "@/utils/notification";
import { themeAppStore } from "@/store/theme";
import JsonPretty from "vue-json-pretty";
import "vue-json-pretty/lib/styles.css";
import type { ConsolePageProps } from "../../types/console";
import type { CanvasEdge, CanvasNode, NodeKind, Position } from "./Type";
import { buildCanvasEdges, buildCanvasNodes } from "./ResourceModel";
import { resourceCategoryList } from "./ResourcePresentation";
import CanvasBoard from "./components/CanvasBoard.vue";
import CanvasResource from "./components/CanvasResource.vue";
import CreatePoolDialog from "../pools/components/CreateDialog.vue";
import CreateSourceDialog from "../sources/components/CreateDialog.vue";
import UploadDialog from "../assets/components/UploadDialog.vue";
import { getAssetProgress, readDroppedFiles, syncAssetProgress } from "../assets/AssetUtils";
import type { StagedFile } from "../assets/AssetUtils";
import SourceBinding from "../sources/components/SourceBinding.vue";
import StatusTag from "../../components/StatusTag.vue";
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
const handleShowLinked = () => boardRef.value?.showLinked(selectedKey.value);
const handleRemoveNode = () => {
  boardRef.value?.removeNode(selectedKey.value);
  handleDeselect();
};
const { t } = useI18n();
const router = useRouter();
const themeStore = themeAppStore();
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
          () => { if (!disposed) emit("refresh"); },
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
const relatedPoolId = ref<string>();
const relatedSourceId = ref<string>();
const relatedAssetId = ref<string>();
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
const selectedAssetPools = computed(
  () =>
    props.libraryData?.asset_pools.filter(
      (pool) =>
        selectedAsset.value && pool.asset_ids.includes(selectedAsset.value.id),
    ) || [],
);
const selectedSourceBindings = computed(() =>
  (props.libraryData?.asset_pools || []).flatMap((pool) =>
    pool.source_statuses
      .filter((binding) => binding.source_id === selectedSource.value?.id)
      .map((binding) => ({ pool, binding })),
  ),
);
const availablePools = computed(
  () =>
    props.libraryData?.asset_pools.filter((pool) =>
      selectedAsset.value
        ? !selectedAsset.value.pending && !pool.asset_ids.includes(selectedAsset.value.id)
        : selectedSource.value &&
          !pool.source_statuses.some(
            (binding) => binding.source_id === selectedSource.value?.id,
          ),
    ) || [],
);
const availableSources = computed(
  () =>
    props.libraryData?.sources.filter(
      (source) =>
        source.type !== "object" &&
        source.id !== props.libraryData?.default_content_source_id &&
        selectedPool.value &&
        !selectedPool.value.source_statuses.some(
          (binding) => binding.source_id === source.id,
        ),
    ) || [],
);
const availableAssets = computed(() =>
  assetList.value.filter(
    (asset) =>
      !asset.pending && selectedPool.value && !selectedPool.value.asset_ids.includes(asset.id),
  ),
);
const selectedEdgePool = computed(() =>
  props.libraryData?.asset_pools.find(
    (pool) => `pool:${pool.id}` === selectedEdge.value?.from,
  ),
);
const selectedEdgeBinding = computed(() =>
  selectedEdgePool.value?.source_statuses.find(
    (binding) => `source:${binding.source_id}` === selectedEdge.value?.to,
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
  if (item.kind === "asset" && assetList.value.find((asset) => asset.id === item.id)?.pending) {
    customNotification("info", t("common.prompt"), t("console.assetPendingHint"));
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
const handleDetach = (edge = selectedEdge.value) => {
  if (!edge) return;
  if (
    edge.content ||
    edge.to === `source:${props.libraryData!.default_content_source_id}` ||
    edge.from.startsWith("asset:")
  ) {
    customNotification(
      "info",
      t("common.prompt"),
      t(
        edge.from.startsWith("asset:")
          ? "console.assetLink"
          : "console.contentLink",
      ),
    );
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
const handleDeleteAsset = () =>
  Modal.confirm({
    title: t("common.delete"),
    content: t("console.deleteAssets", { count: 1 }),
    okType: "danger",
    async onOk() {
      const id = selectedAsset.value!.id;
      await requestAssetDelete(props.libraryData!.name, {
        asset_ids: [id],
      });
      boardRef.value?.removeNode(selectedKey.value);
      handleDeselect();
      progress.remove([id]);
      await queryAssetList();
      emit("refresh");
    },
  });
const handleDeletePool = () =>
  Modal.confirm({
    title: t("common.delete"),
    content: t("console.deletePool", { name: selectedPool.value!.name }),
    okType: "danger",
    async onOk() {
      await requestAssetPoolDelete(
        props.libraryData!.name,
        selectedPool.value!.id,
      );
      boardRef.value?.removeNode(selectedKey.value);
      handleDeselect();
      emit("refresh");
    },
  });
const handleDeleteSource = () =>
  Modal.confirm({
    title: t("common.delete"),
    content: t("console.deleteSource", { name: selectedSource.value!.name }),
    okType: "danger",
    async onOk() {
      await requestSourceDelete(
        props.libraryData!.name,
        selectedSource.value!.id,
      );
      boardRef.value?.removeNode(selectedKey.value);
      handleDeselect();
      emit("refresh");
    },
  });
watch(selectedKey, () => {
  relatedPoolId.value = undefined;
  relatedSourceId.value = undefined;
  relatedAssetId.value = undefined;
});
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
.detail-title {
  margin-bottom: 16px;
  .resource-id {
    display: block;
    margin-top: 8px;
    font-size: 12px;
    color: var(--font-info-color);
    overflow-wrap: anywhere;
  }
}
.detail-action {
  margin-top: 20px;
}
.stats-wrap {
  padding: 12px;
  border-radius: 8px;
  background: var(--bg-card-color);
  margin-bottom: 16px;
  :deep(.intel-statistic-content) {
    font-size: 22px;
  }
}
.configuration-wrap {
  margin: 16px 0;
}
.link-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 20px;
  margin-bottom: 20px;
  background: var(--bg-card-color);
  border-radius: 8px;
  color: var(--font-main-color);
}
.association-wrap {
  margin: 16px 0;
}
.association-controls {
  display: flex;
  gap: 8px;
  .intel-select {
    flex: 1;
    min-width: 0;
  }
}
.section-hint {
  color: var(--font-info-color);
  font-size: 12px;
  line-height: 1.7;
  margin-top: 10px;
}
.detail-notice {
  margin: 16px 0;
}
.pool-information :deep(.intel-collapse-content-box) {
  padding: 0 0 12px;
}
h4 {
  margin: 12px 0 8px;
  color: var(--font-main-color);
  font-size: 13px;
}
</style>
