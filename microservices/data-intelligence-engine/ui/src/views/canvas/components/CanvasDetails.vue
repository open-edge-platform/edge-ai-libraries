<template>
  <a-drawer
    :open="open"
    :title="drawerTitle"
    width="min(600px, 100vw)"
    :mask="false"
    class="canvas-inspector"
    @close="emit('close')"
  >
    <div class="detail-body">
      <template v-if="node">
        <div class="detail-title">
          <CanvasResource :node="node" />
          <a-typography-text copyable class="resource-id">{{
            node.id
          }}</a-typography-text>
        </div>
        <AssetDetails
          v-if="node.kind === 'asset' && selectedAsset"
          :key="`asset:${node.id}`"
          :asset="selectedAsset"
          :library-data="libraryData"
          :submit-loading="submitLoading"
          @connect="handleConnect"
          @remove-node="emit('remove-node', node.key)"
          @delete="emit('delete-asset')"
        />
        <PoolDetails
          v-else-if="node.kind === 'pool' && selectedPool"
          :key="`pool:${node.id}`"
          :pool="selectedPool"
          :library-data="libraryData"
          :assets="assets"
          :submit-loading="submitLoading"
          @connect="handleConnect"
          @add-assets="
            (poolId, assetIds) => emit('add-assets', poolId, assetIds)
          "
          @detach="emit('detach', $event)"
          @select="emit('select', $event)"
          @search="emit('search')"
          @manage="emit('manage', $event)"
          @upload="emit('upload', $event)"
          @retrieve="emit('retrieve', $event)"
          @delete="emit('delete-pool')"
        />
        <SourceDetails
          v-else-if="node.kind === 'source' && selectedSource"
          :key="`source:${node.id}`"
          :source="selectedSource"
          :node="node"
          :library-data="libraryData"
          :submit-loading="submitLoading"
          @connect="handleConnect"
          @detach="emit('detach', $event)"
          @search="emit('search')"
          @delete="emit('delete-source')"
        />
      </template>
      <template v-else-if="edge">
        <LinkDetails
          :edge="edge"
          :library-data="libraryData"
          :node-list="nodeList"
          :assets="assets"
          :submit-loading="submitLoading"
          @detach="emit('detach', $event)"
          @search="emit('search')"
        />
      </template>
      <template v-else>
        <LibraryDetails
          :library-data="libraryData"
          @retrieve="emit('retrieve')"
        />
      </template>
    </div>
    <template #footer
      ><span class="section-hint">{{
        $t("console.canvasKeyboardHint")
      }}</span></template
    >
  </a-drawer>
</template>
<script lang="ts" setup name="CanvasDetails">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import "vue-json-pretty/lib/styles.css";
import type { Library } from "@/api/console/type";
import type { AssetRow } from "../../assets/AssetProgress";
import type { CanvasEdge, CanvasNode } from "../Type";
import CanvasResource from "./CanvasResource.vue";
import AssetDetails from "./AssetDetails.vue";
import PoolDetails from "./PoolDetails.vue";
import SourceDetails from "./SourceDetails.vue";
import LinkDetails from "./LinkDetails.vue";
import LibraryDetails from "./LibraryDetails.vue";

const props = defineProps<{
  open: boolean;
  libraryData: Library;
  node?: CanvasNode;
  edge?: CanvasEdge;
  nodeList: CanvasNode[];
  assets: AssetRow[];
  submitLoading: boolean;
}>();
const emit = defineEmits<{
  close: [];
  connect: [from: string, to: string];
  "add-assets": [poolId: string, assetIds: string[]];
  detach: [edge: CanvasEdge];
  select: [key: string];
  search: [];
  manage: [id: string];
  upload: [id: string];
  retrieve: [id?: string];
  "remove-node": [key: string];
  "delete-asset": [];
  "delete-pool": [];
  "delete-source": [];
}>();
const { t } = useI18n();
const drawerTitle = computed(() => {
  if (props.node) return t(`console.${props.node.kind}Details`);
  if (!props.edge) return t("console.libraryDetails");
  if (props.edge.content) return t("console.contentLinkDetails");
  if (props.edge.from.startsWith("asset:"))
    return t("console.assetLinkDetails");
  return t("console.sourceLinkDetails");
});
const handleConnect = (from: string, to: string) => emit("connect", from, to);
const selectedAsset = computed(() =>
  props.assets.find((asset) => asset.id === props.node?.id),
);
const selectedPool = computed(() =>
  props.libraryData.asset_pools.find((pool) => pool.id === props.node?.id),
);
const selectedSource = computed(() =>
  props.libraryData.sources.find((source) => source.id === props.node?.id),
);
</script>
<style scoped lang="less">
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
.detail-body {
  :deep(.detail-action) {
    margin-top: 20px;
  }
  :deep(.stats-wrap) {
    padding: 12px;
    border-radius: 8px;
    background: var(--bg-card-color);
    margin-bottom: 16px;
    .intel-statistic-content {
      font-size: 22px;
    }
  }
  :deep(.configuration-wrap) {
    margin: 16px 0;
  }
  :deep(.association-wrap) {
    margin: 16px 0;
  }
  :deep(.association-controls) {
    display: flex;
    gap: 8px;
    .intel-select {
      flex: 1;
      min-width: 0;
    }
  }

  :deep(h4) {
    margin: 12px 0 8px;
    color: var(--font-main-color);
    font-size: 13px;
  }
}
.section-hint,
.detail-body :deep(.section-hint) {
  color: var(--font-info-color);
  font-size: 12px;
  line-height: 1.7;
  margin-top: 10px;
}
</style>
