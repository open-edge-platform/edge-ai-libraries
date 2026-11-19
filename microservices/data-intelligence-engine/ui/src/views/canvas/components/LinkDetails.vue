<template>
  <div class="link-summary">
    <div class="link-endpoint">
      <span class="link-label">{{
        $t(edge.from.startsWith("asset:") ? "console.assets" : "console.pools")
      }}</span>
      <span class="link-name">{{
        nodeList.find((item) => item.key === edge.from)?.name ||
        edge.from.split(":").slice(1).join(":")
      }}</span>
    </div>
    <ArrowDownOutlined class="link-direction" />

    <div class="link-endpoint link-destination">
      <span class="link-label">{{
        $t(edge.to.startsWith("pool:") ? "console.pools" : "console.sources")
      }}</span>
      <span class="link-name">{{
        nodeList.find((item) => item.key === edge.to)?.name ||
        edge.to.split(":").slice(1).join(":")
      }}</span>
    </div>
  </div>
  <SourceBinding
    v-if="selectedPool && selectedBinding"
    :library-data="libraryData"
    :pool="selectedPool"
    :binding="selectedBinding"
    @search="emit('search')"
  />
  <a-alert
    v-if="edge.content"
    type="info"
    showIcon
    :message="$t('console.contentLink')"
  />
  <template v-else>
    <p class="section-hint">
      {{
        $t(
          edge.from.startsWith("asset:")
            ? "console.removePoolAssetHint"
            : "console.detachHint",
        )
      }}
    </p>
    <a-tooltip :title="detachHint">
      <a-button
        danger
        :loading="submitLoading"
        :disabled="detachDisabled"
        @click="emit('detach', edge)"
      >
        {{
          $t(
            edge.from.startsWith("asset:")
              ? "console.removeOneFromPool"
              : "console.detach",
          )
        }}
      </a-button>
    </a-tooltip>
  </template>
</template>
<script lang="ts" setup name="CanvasLinkDetails">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { ArrowDownOutlined } from "@ant-design/icons-vue";
import type { Library } from "@/api/console/type";
import {
  isAssetDeletionBlocked,
  type AssetRow,
} from "../../assets/AssetProgress";
import type { CanvasEdge, CanvasNode } from "../Type";
import SourceBinding from "../../sources/components/SourceBinding.vue";

const props = defineProps<{
  edge: CanvasEdge;
  libraryData: Library;
  nodeList: CanvasNode[];
  assets: AssetRow[];
  submitLoading: boolean;
}>();
const emit = defineEmits<{ detach: [edge: CanvasEdge]; search: [] }>();
const { t } = useI18n();
const linkedAsset = computed(() =>
  props.edge.from.startsWith("asset:")
    ? props.assets.find((asset) => `asset:${asset.id}` === props.edge.from)
    : undefined,
);
const sourceIndexing = computed(
  () =>
    props.edge.to.startsWith("source:") &&
    props.nodeList.some(
      (node) => node.key === props.edge.to && node.status === "indexing",
    ),
);
const selectedPool = computed(() =>
  props.libraryData.asset_pools.find(
    (pool) => `pool:${pool.id}` === props.edge.from,
  ),
);
const detachDisabled = computed(
  () =>
    sourceIndexing.value ||
    selectedPool.value?.display_status === "indexing" ||
    (!!linkedAsset.value &&
      isAssetDeletionBlocked(linkedAsset.value, props.libraryData.asset_pools)),
);
const detachHint = computed(() => {
  if (sourceIndexing.value) return t("console.sourceIndexingDeleteHint");
  if (selectedPool.value?.display_status === "indexing")
    return t("console.poolIndexingDeleteHint");
  if (linkedAsset.value?.pending) return t("console.assetPendingHint");
  if (detachDisabled.value) return t("console.assetIndexingDeleteHint");
  return undefined;
});
const selectedBinding = computed(() =>
  selectedPool.value?.source_statuses.find(
    (binding) => `source:${binding.source_id}` === props.edge.to,
  ),
);
</script>
<style scoped lang="less">
.link-summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 4px 0 20px;
}
.link-endpoint {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 6px 8px;
  border: 1px dashed var(--color-primary-second);
  border-left: 3px solid var(--color-primary-second);
  border-radius: 0 6px 6px 0;
  margin-top: 8px;
}
.link-destination {
  border-color: var(--color-purple);
  margin-top: 0;
}
.link-label {
  position: absolute;
  top: 0;
  left: 10px;
  transform: translateY(-50%);
  padding: 1px 6px;
  background: var(--bg-content-color);
  color: var(--color-primary-second);
  font-size: 11px;
  font-weight: 500;
  line-height: 1.4;
  white-space: nowrap;
}
.link-destination .link-label {
  color: var(--color-purple);
}
.link-name {
  color: var(--font-main-color);
  font-weight: 500;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.link-direction {
  align-self: center;
  margin-left: 5px;
  color: var(--color-success);
  font-size: 16px;
  font-weight: 700;
}
.section-hint {
  color: var(--font-info-color);
  font-size: 12px;
  line-height: 1.7;
  margin: 12px 0;
}
</style>
