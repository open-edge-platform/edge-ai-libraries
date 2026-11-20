<template>
  <a-row :gutter="16" class="stats-wrap">
    <a-col :span="8"
      ><a-statistic
        :title="$t('console.assets')"
        :value="pool.asset_ids.length"
    /></a-col>
    <a-col :span="8"
      ><a-statistic
        :title="$t('console.sources')"
        :value="pool.source_statuses.length"
    /></a-col>
    <a-col :span="8"
      ><a-statistic :title="$t('console.revision')" :value="pool.revision"
    /></a-col>
  </a-row>
  <SourceBinding
    v-for="binding in pool.source_statuses"
    :key="binding.source_id"
    :library-data="libraryData"
    :pool="pool"
    :binding="binding"
    removable
    :pool-indexing="poolIndexing"
    @search="emit('search')"
    @detach="
      emit('detach', {
        from: `pool:${pool.id}`,
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
        @click="emit('connect', `pool:${pool.id}`, `source:${relatedSourceId}`)"
      >
        {{ $t("console.add") }}
      </a-button>
    </div>
  </div>
  <a-collapse class="pool-information">
    <a-collapse-panel
      key="assets"
      :header="`${$t('console.poolAssets')} (${pool.asset_ids.length})`"
    >
      <div v-if="pool.asset_ids.length" class="pool-assets-toolbar">
        <a-checkbox
          :checked="
            selectedAssetIds.length === removableAssetIds.length &&
            !!removableAssetIds.length
          "
          :indeterminate="
            selectedAssetIds.length > 0 &&
            selectedAssetIds.length < removableAssetIds.length
          "
          :disabled="!removableAssetIds.length"
          @change="handleSelectAllPoolAssets"
          >{{ $t("common.all") }}</a-checkbox
        >
        <a-button
          danger
          size="small"
          :disabled="
            !selectedAssetIds.length ||
            submitLoading ||
            selectedAssetIds.some(assetRemovalBlocked)
          "
          :title="
            selectedAssetIds.some(assetRemovalBlocked)
              ? $t('console.assetIndexingDeleteHint')
              : undefined
          "
          @click="handleRemoveAssets(selectedAssetIds)"
          >{{
            $t("console.removeFromPool", { count: selectedAssetIds.length })
          }}</a-button
        >
      </div>
      <a-list
        :data-source="pool.asset_ids"
        :pagination="
          pool.asset_ids.length > 10 ? { pageSize: 10, size: 'small' } : false
        "
        size="small"
        class="pool-asset-list"
      >
        <template #renderItem="{ item }">
          <a-list-item>
            <a-checkbox
              :checked="selectedAssetIds.includes(item)"
              :disabled="assetRemovalBlocked(item)"
              :aria-label="
                $t('console.selectAsset', {
                  name: assets.find((asset) => asset.id === item)?.name || item,
                })
              "
              @change="toggleAssetSelection(item)"
            />
            <div class="pool-asset-info">
              <a @click="emit('select', `asset:${item}`)">{{
                assets.find((asset) => asset.id === item)?.name || item
              }}</a>
              <span>{{ item }}</span>
            </div>
            <a-button
              danger
              size="small"
              :disabled="submitLoading || assetRemovalBlocked(item)"
              :title="
                assetRemovalBlocked(item)
                  ? $t('console.assetIndexingDeleteHint')
                  : $t('console.removeOneFromPool')
              "
              :aria-label="$t('console.removeOneFromPool')"
              @click="handleRemoveAssets([item])"
              ><template #icon><DeleteOutlined /></template
            ></a-button>
          </a-list-item>
        </template>
      </a-list>
    </a-collapse-panel>
    <a-collapse-panel key="metadata" :header="$t('console.metadata')">
      <JsonPretty
        :data="pool.metadata"
        :theme="themeStore.theme === 'dark' ? 'dark' : 'light'"
      />
    </a-collapse-panel>
  </a-collapse>
  <div v-if="availableAssets.length" class="association-wrap">
    <h4>{{ $t("console.addAssets") }}</h4>
    <div class="association-controls">
      <a-select
        v-model:value="relatedAssetIds"
        mode="multiple"
        showSearch
        optionFilterProp="label"
        :maxTagCount="2"
        :placeholder="$t('console.pleaseSelect')"
        :options="
          availableAssets.map((asset) => ({
            value: asset.id,
            label: asset.name || asset.id,
          }))
        "
      >
        <template #dropdownRender="{ menuNode }">
          <div class="select-all" @mousedown.prevent>
            <a-checkbox
              :checked="
                relatedAssetIds.length === availableAssets.length &&
                !!availableAssets.length
              "
              :indeterminate="
                relatedAssetIds.length > 0 &&
                relatedAssetIds.length < availableAssets.length
              "
              @change="handleSelectAllAssets"
              >{{ $t("common.all") }}</a-checkbox
            >
          </div>
          <component :is="menuNode" />
        </template>
      </a-select>
      <a-button
        :loading="submitLoading"
        :disabled="!relatedAssetIds.length"
        @click="emit('add-assets', pool.id, relatedAssetIds)"
      >
        {{ $t("console.add") }}
      </a-button>
    </div>
  </div>
  <p class="section-hint">{{ $t("console.poolHint") }}</p>
  <a-space wrap class="detail-action">
    <a-button type="primary" ghost @click="emit('manage', pool.id)">{{
      $t("console.manage")
    }}</a-button>
    <a-button @click="emit('upload', pool.id)">{{
      $t("console.upload")
    }}</a-button>
    <a-button @click="emit('retrieve', pool.id)">{{
      $t("console.retrieve")
    }}</a-button>
    <a-button
      danger
      :disabled="poolIndexing"
      :title="poolIndexing ? $t('console.poolIndexingDeleteHint') : undefined"
      @click="emit('delete')"
      >{{ $t("common.delete") }}</a-button
    >
  </a-space>
</template>
<script lang="ts" setup name="CanvasPoolDetails">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Modal } from "ant-design-vue";
import { DeleteOutlined } from "@ant-design/icons-vue";
import JsonPretty from "vue-json-pretty";
import {
  requestAssetPoolAssetDelete,
  requestAssetPoolAssetsDelete,
} from "@/api/console";
import type { AssetPool, Library } from "@/api/console/type";
import { themeAppStore } from "@/store/theme";
import {
  isAssetDeletionBlocked,
  type AssetRow,
} from "../../assets/AssetProgress";
import type { CanvasEdge } from "../Type";
import SourceBinding from "../../sources/components/SourceBinding.vue";

const props = defineProps<{
  pool: AssetPool;
  libraryData: Library;
  assets: AssetRow[];
  submitLoading: boolean;
}>();
const emit = defineEmits<{
  connect: [from: string, to: string];
  "add-assets": [poolId: string, assetIds: string[]];
  detach: [edge: CanvasEdge];
  select: [key: string];
  search: [];
  manage: [id: string];
  upload: [id: string];
  retrieve: [id: string];
  delete: [];
}>();
const themeStore = themeAppStore();
const { t } = useI18n();
const poolIndexing = computed(() => props.pool.display_status === "indexing");
const relatedSourceId = ref<string>();
const relatedAssetIds = ref<string[]>([]);
const selectedAssetIds = ref<string[]>([]);
const assetRemovalBlocked = (id: string) => {
  const asset = props.assets.find((item) => item.id === id);
  return (
    poolIndexing.value ||
    !asset ||
    isAssetDeletionBlocked(asset, props.libraryData.asset_pools)
  );
};
const removableAssetIds = computed(() =>
  props.pool.asset_ids.filter((id) => !assetRemovalBlocked(id)),
);
const handleSelectAllPoolAssets = () => {
  selectedAssetIds.value =
    selectedAssetIds.value.length === removableAssetIds.value.length
      ? []
      : [...removableAssetIds.value];
};
const toggleAssetSelection = (id: string) => {
  selectedAssetIds.value = selectedAssetIds.value.includes(id)
    ? selectedAssetIds.value.filter((selected) => selected !== id)
    : [...selectedAssetIds.value, id];
};
const handleRemoveAssets = (ids: string[]) => {
  const requested = [...ids];
  if (!requested.length || requested.some(assetRemovalBlocked)) return;
  Modal.confirm({
    title: t("console.removeOneFromPool"),
    content: t("console.removePoolAssetsConfirm", { count: requested.length }),
    okType: "danger",
    okText: t("common.confirm"),
    cancelText: t("common.cancel"),
    async onOk() {
      if (requested.some(assetRemovalBlocked)) return;
      if (requested.length === 1)
        await requestAssetPoolAssetDelete(
          props.libraryData.name,
          props.pool.id,
          requested[0],
        );
      else
        await requestAssetPoolAssetsDelete(
          props.libraryData.name,
          props.pool.id,
          { asset_ids: requested },
        );
      selectedAssetIds.value = selectedAssetIds.value.filter(
        (id) => !requested.includes(id),
      );
      emit("search");
    },
  });
};
const availableSources = computed(() =>
  props.libraryData.sources.filter(
    (source) =>
      source.type !== "object" &&
      source.id !== props.libraryData.default_content_source_id &&
      !props.pool.source_statuses.some(
        (binding) => binding.source_id === source.id,
      ),
  ),
);
const availableAssets = computed(() =>
  props.assets.filter(
    (asset) => !asset.pending && !props.pool.asset_ids.includes(asset.id),
  ),
);
const handleSelectAllAssets = () => {
  relatedAssetIds.value =
    relatedAssetIds.value.length === availableAssets.value.length
      ? []
      : availableAssets.value.map((asset) => asset.id);
};
watch(availableAssets, (assets) => {
  const availableIds = new Set(assets.map((asset) => asset.id));
  relatedAssetIds.value = relatedAssetIds.value.filter((id) =>
    availableIds.has(id),
  );
});
watch(removableAssetIds, (ids) => {
  selectedAssetIds.value = selectedAssetIds.value.filter((id) =>
    ids.includes(id),
  );
});
</script>
<style scoped lang="less">
.pool-information {
  margin: 20px 0;
  border: 1px solid var(--border-main-color);
  border-radius: 6px;
  overflow: hidden;
  background: var(--bg-content-color);
  :deep(.intel-collapse-item + .intel-collapse-item) {
    border-top: 1px solid var(--border-main-color);
  }
  :deep(.intel-collapse-header) {
    align-items: center;
    padding: 10px 14px;
    color: var(--font-main-color);
    font-weight: 500;
  }
  :deep(.intel-collapse-content-box) {
    padding: 0 12px 12px;
  }
}
.pool-assets-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 0;
}
.pool-asset-list :deep(.intel-list-item) {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
}
.pool-asset-info {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  overflow-wrap: anywhere;
  a {
    color: var(--font-main-color);
    font-weight: 500;
    line-height: 1.4;
    &:hover {
      color: var(--color-primary-second);
      text-decoration: underline;
    }
  }
  span {
    color: var(--font-info-color);
    font-size: 11px;
    line-height: 1.5;
  }
}
.select-all {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-main-color);
}
</style>
