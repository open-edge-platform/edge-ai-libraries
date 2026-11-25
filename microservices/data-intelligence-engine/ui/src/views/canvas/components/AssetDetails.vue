<template>
  <a-descriptions :column="1" bordered size="small">
    <a-descriptions-item :label="$t('console.origin')">{{
      asset.origin
    }}</a-descriptions-item>
    <a-descriptions-item :label="$t('console.kind')">
      {{
        $te(`console.${asset.kind}`) ? $t(`console.${asset.kind}`) : asset.kind
      }}
    </a-descriptions-item>
    <a-descriptions-item :label="$t('console.mediaType')">
      {{ asset.media_type || "—" }}
    </a-descriptions-item>
    <a-descriptions-item :label="$t('console.contentSource')">
      {{
        libraryData.sources.find(
          (source) => source.id === asset.content_source_id,
        )?.name ||
        asset.content_source_id ||
        "—"
      }}
    </a-descriptions-item>
    <a-descriptions-item :label="$t('console.pools')">
      <a-tag v-for="pool in assetPools" :key="pool.id">{{ pool.name }}</a-tag>
      <span v-if="!assetPools.length">{{ $t("console.none") }}</span>
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
          availablePools.map((pool) => ({ value: pool.id, label: pool.name }))
        "
      />
      <a-button
        :loading="submitLoading"
        :disabled="!relatedPoolId"
        @click="emit('connect', `asset:${asset.id}`, `pool:${relatedPoolId}`)"
      >
        {{ $t("console.add") }}
      </a-button>
    </div>
  </div>
  <a-space class="detail-action">
    <a-button @click="emit('remove-node')">{{
      $t("console.removeCanvas")
    }}</a-button>
    <a-button
      danger
      :disabled="deleteDisabled"
      :title="deleteHint"
      @click="emit('delete')"
      >{{ $t("common.delete") }}</a-button
    >
  </a-space>
</template>
<script lang="ts" setup name="CanvasAssetDetails">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import type { Library } from "@/api/console/type";
import {
  isAssetDeletionBlocked,
  type AssetRow,
} from "../../assets/AssetProgress";

const props = defineProps<{
  asset: AssetRow;
  libraryData: Library;
  submitLoading: boolean;
}>();
const emit = defineEmits<{
  connect: [from: string, to: string];
  "remove-node": [];
  delete: [];
}>();
const { t } = useI18n();
const deleteDisabled = computed(() =>
  isAssetDeletionBlocked(props.asset, props.libraryData.asset_pools),
);
const deleteHint = computed(() => {
  if (props.asset.pending) return t("console.assetPendingHint");
  if (deleteDisabled.value) return t("console.assetIndexingDeleteHint");
  return undefined;
});
const relatedPoolId = ref<string>();
const assetPools = computed(() =>
  props.libraryData.asset_pools.filter((pool) =>
    pool.asset_ids.includes(props.asset.id),
  ),
);
const availablePools = computed(() =>
  props.asset.pending
    ? []
    : props.libraryData.asset_pools.filter(
        (pool) => !pool.asset_ids.includes(props.asset.id),
      ),
);
</script>
