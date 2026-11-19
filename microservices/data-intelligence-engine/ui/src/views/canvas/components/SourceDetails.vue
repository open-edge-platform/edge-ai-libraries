<template>
  <a-descriptions :column="1" bordered size="small">
    <a-descriptions-item :label="$t('console.type')">
      {{
        $te(`console.${source.type}Source`)
          ? $t(`console.${source.type}Source`)
          : source.type
      }}
    </a-descriptions-item>
    <a-descriptions-item :label="$t('console.database')">{{
      source.database_id
    }}</a-descriptions-item>
    <a-descriptions-item :label="$t('console.collection')">{{
      source.collection_name
    }}</a-descriptions-item>
    <a-descriptions-item :label="$t('console.status')">
      {{ $t(source.enabled ? "console.enabled" : "console.DISABLED") }}
    </a-descriptions-item>
    <a-descriptions-item :label="$t('console.validation')">
      <StatusTag :value="source.reconciled ? 'reconciled' : 'unreconciled'" />
    </a-descriptions-item>
    <a-descriptions-item v-if="node.content" :label="$t('console.role')">
      {{ $t("console.defaultContent") }}
    </a-descriptions-item>
  </a-descriptions>
  <a-alert
    v-if="source.reconciliation_error"
    type="error"
    showIcon
    :message="source.reconciliation_error"
    class="detail-notice"
  />
  <div class="configuration-wrap">
    <h4>{{ $t("console.sourceConfiguration") }}</h4>
    <JsonPretty
      :data="source.operator_options"
      :theme="themeStore.theme === 'dark' ? 'dark' : 'light'"
    />
    <p class="section-hint">{{ $t("console.sourcesHint") }}</p>
  </div>
  <h4>{{ $t("console.inUseBy") }}</h4>
  <template v-if="node.content">
    <a-tag v-for="pool in libraryData.asset_pools" :key="pool.id">{{
      pool.name
    }}</a-tag>
    <p class="section-hint">{{ $t("console.contentLink") }}</p>
  </template>
  <template v-else>
    <div v-for="entry in sourceBindings" :key="entry.pool.id">
      <h4>{{ entry.pool.name }}</h4>
      <SourceBinding
        :library-data="libraryData"
        :pool="entry.pool"
        :binding="entry.binding"
        removable
        @search="emit('search')"
        @detach="
          emit('detach', {
            from: `pool:${entry.pool.id}`,
            to: `source:${source.id}`,
          })
        "
      />
    </div>
    <p v-if="!sourceBindings.length" class="section-hint">
      {{ $t("console.none") }}
    </p>
    <div
      v-if="availablePools.length && source.type !== 'object'"
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
            availablePools.map((pool) => ({ value: pool.id, label: pool.name }))
          "
        />
        <a-button
          :loading="submitLoading"
          :disabled="!relatedPoolId"
          @click="
            emit('connect', `pool:${relatedPoolId}`, `source:${source.id}`)
          "
        >
          {{ $t("console.add") }}
        </a-button>
      </div>
    </div>
  </template>
  <a-tooltip
    :title="
      node.status === 'indexing'
        ? $t('console.sourceIndexingDeleteHint')
        : undefined
    "
  >
    <a-button
      danger
      :disabled="node.status === 'indexing'"
      @click="emit('delete')"
      >{{ $t("common.delete") }}</a-button
    >
  </a-tooltip>
</template>
<script lang="ts" setup name="CanvasSourceDetails">
import { computed, ref } from "vue";
import JsonPretty from "vue-json-pretty";
import type { Library, Source } from "@/api/console/type";
import { themeAppStore } from "@/store/theme";
import type { CanvasEdge, CanvasNode } from "../Type";
import SourceBinding from "../../sources/components/SourceBinding.vue";
import StatusTag from "../../../components/StatusTag.vue";

const props = defineProps<{
  source: Source;
  node: CanvasNode;
  libraryData: Library;
  submitLoading: boolean;
}>();
const emit = defineEmits<{
  connect: [from: string, to: string];
  detach: [edge: CanvasEdge];
  search: [];
  delete: [];
}>();
const themeStore = themeAppStore();
const relatedPoolId = ref<string>();
const sourceBindings = computed(() =>
  props.libraryData.asset_pools.flatMap((pool) =>
    pool.source_statuses
      .filter((binding) => binding.source_id === props.source.id)
      .map((binding) => ({ pool, binding })),
  ),
);
const availablePools = computed(() =>
  props.libraryData.asset_pools.filter(
    (pool) =>
      !pool.source_statuses.some(
        (binding) => binding.source_id === props.source.id,
      ),
  ),
);
</script>
