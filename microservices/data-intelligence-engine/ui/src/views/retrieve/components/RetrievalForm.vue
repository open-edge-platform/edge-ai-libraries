<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-form layout="vertical" class="retrieval-form">
    <div class="section-title">
      <span>01</span>
      {{ $t("console.retrievalScope") }}
    </div>
    <a-form-item :label="$t('console.pools')">
      <a-select
        v-model:value="form.pool"
        :placeholder="$t('console.pleaseSelect')"
        :options="[
          { value: '', label: $t('console.allPools') },
          ...libraryData.asset_pools.map((item) => ({
            value: item.id,
            label: item.name,
          })),
        ]"
      />
    </a-form-item>
    <a-form-item required>
      <template #label>
        {{ $t("console.modalities") }}
        <FormTooltip :title="$t('console.modalitiesHint')" />
      </template>
      <a-checkbox-group
        :value="form.modalities"
        class="modality-options"
        @change="handleModalitiesChange"
      >
        <a-checkbox
          v-for="type in ['document', 'image', 'video', 'audio']"
          :key="type"
          :value="type"
        >
          {{ $t(`console.${type}`) }}
        </a-checkbox>
      </a-checkbox-group>
    </a-form-item>
    <div class="section-title">
      <span>02</span>
      {{ $t("console.retrievalSettings") }}
    </div>
    <a-form-item v-if="form.modalities.includes('document')">
      <template #label>
        {{ $t("console.retrieverType") }}
        <FormTooltip
          :title="
            $t(
              form.type === 'graph'
                ? 'console.graphHintRetrieval'
                : `console.${form.type}Hint`,
            )
          "
        />
      </template>
      <a-select
        v-model:value="form.type"
        :placeholder="$t('console.pleaseSelect')"
      >
        <a-select-option
          v-for="type in ['rrf', 'vectorsimilarity', 'bm25', 'graph']"
          :key="type"
          :value="type"
        >
          {{ $t(`console.${type}`) }}
        </a-select-option>
      </a-select>
    </a-form-item>
    <a-form-item :label="$t('console.topK')">
      <div class="slider-wrap">
        <a-slider v-model:value="form.topK" :min="1" :max="100" />
        <a-input-number
          v-model:value="form.topK"
          placeholder="5"
          :min="1"
          :max="100"
          :precision="0"
        />
      </div>
    </a-form-item>
    <a-form-item :label="$t('console.postprocess')">
      <a-select
        v-model:value="form.reranker"
        :placeholder="$t('console.pleaseSelect')"
      >
        <a-select-option value="">{{
          defaultRerankerModel || "—"
        }}</a-select-option>
        <a-select-option
          v-for="model in modelData.reranker?.models.filter(
            (item) => !item.media && item.name !== defaultRerankerModel,
          )"
          :key="model.name"
          :value="model.name"
        >
          {{ model.name }}
        </a-select-option>
        <a-select-option value="__none__">
          {{ $t("console.none") }}
        </a-select-option>
      </a-select>
    </a-form-item>
    <a-form-item
      v-if="form.reranker !== '__none__'"
      :label="$t('console.topN')"
    >
      <div class="slider-wrap">
        <a-slider v-model:value="form.topN" :min="1" :max="50" />
        <a-input-number
          v-model:value="form.topN"
          placeholder="3"
          :min="1"
          :max="50"
          :precision="0"
        />
      </div>
    </a-form-item>
    <a-collapse ghost class="advanced-wrap">
      <a-collapse-panel key="advanced" :header="$t('console.advanced')">
        <template v-if="form.reranker !== '__none__'">
          <a-form-item>
            <template #label>
              {{ $t("console.rerankQuery") }}
              <FormTooltip :title="$t('console.rerankQueryHint')" />
            </template>
            <a-input
              v-model:value="form.rerankQuery"
              :placeholder="$t('console.rerankQueryPlaceholder')"
            />
          </a-form-item>
          <a-form-item :label="$t('console.backend')">
            <a-select
              v-model:value="form.backend"
              :placeholder="$t('console.pleaseSelect')"
            >
              <a-select-option value="">
                {{ $t("console.engineDefault") }}
              </a-select-option>
              <a-select-option
                v-for="backend in modelData.reranker?.backends"
                :key="backend"
                :value="backend"
              >
                {{ backend }}
              </a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item>
            <template #label>
              {{ $t("console.device") }}
              <FormTooltip
                :title="
                  effectiveRerankerMedia
                    ? $t('console.vlDeviceHint')
                    : $t('console.inheritEngineHint')
                "
              />
            </template>
            <a-select
              v-model:value="form.device"
              :loading="devicesLoading"
              :placeholder="rerankerDevicePlaceholder"
              :options="[
                { value: '', label: rerankerDevicePlaceholder },
                ...deviceList.map((value) => ({ value, label: value })),
              ]"
            />
          </a-form-item>
          <a-form-item :label="$t('console.modelId')">
            <a-input
              v-model:value="form.model"
              :placeholder="rerankerModelPlaceholder"
            />
          </a-form-item>
          <a-form-item :label="$t('console.apiBase')">
            <a-input
              v-model:value="form.apiBase"
              :placeholder="
                modelData.reranker?.api_base || 'http://host:port/v1'
              "
            />
          </a-form-item>
        </template>
        <a-form-item>
          <template #label>
            {{ $t("console.excludeChunks") }}
            <FormTooltip :title="$t('console.excludeChunksHint')" />
          </template>
          <a-textarea
            v-model:value="form.excluded"
            :rows="3"
            placeholder="chunk-id-1&#10;chunk-id-2"
          />
        </a-form-item>
      </a-collapse-panel>
    </a-collapse>
  </a-form>
</template>
<script lang="ts" setup name="RetrievalForm">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import FormTooltip from "@/components/FormTooltip.vue";
import { getModelDevices, getModelList, requestRetrieval } from "@/api/console";
import { Local } from "@/utils/storage";
import type {
  Library,
  ModelOptions,
  RetrieveRequest,
} from "@/api/console/type";
import { inferRerankerBackend, isMediaReranker } from "../RerankerModel";
const props = defineProps<{ libraryData: Library }>();
const route = useRoute();
const { t } = useI18n();
const modelData = ref<Record<string, ModelOptions>>({});
const deviceList = ref<string[]>([]);
const devicesLoading = ref(false);
const storageKey = `console.retrieval.${props.libraryData.name}`;
const defaults = {
  pool: "",
  topK: 5,
  topN: 3,
  type: "rrf",
  modalities: ["document"],
  reranker: "",
  rerankQuery: "",
  backend: "",
  device: "",
  model: "",
  apiBase: "",
  excluded: "",
};
const stored = Local.get(storageKey) as Partial<typeof defaults> | null;
const form = reactive({
  ...defaults,
  ...stored,
  pool:
    typeof route.query.pool === "string"
      ? route.query.pool
      : props.libraryData.asset_pools.some((pool) => pool.id === stored?.pool)
        ? stored!.pool!
        : "",
});
watch(form, () => Local.set(storageKey, form));
const handleModalitiesChange = (values: Array<string | number | boolean>) => {
  if (!values.length) return;
  const selected = values.map(String);
  if (selected.includes("video") && !form.modalities.includes("video")) {
    form.modalities = ["video"];
  } else {
    form.modalities = selected.filter(
      (type) => type !== "video" || selected.length === 1,
    );
  }
};
const mediaSearch = computed(() =>
  form.modalities.some((item) => item !== "document"),
);
const defaultRerankerModel = computed(() => {
  const options = modelData.value.reranker;
  return (
    (mediaSearch.value ? options?.media_model_id : options?.model_id) || ""
  );
});
const effectiveRerankerBackend = computed(() =>
  inferRerankerBackend(
    modelData.value.reranker,
    {
      backend: form.backend,
      model_id: form.model.trim() || form.reranker,
    },
    mediaSearch.value,
  ),
);
const effectiveRerankerMedia = computed(() =>
  isMediaReranker(
    modelData.value.reranker,
    {
      backend: form.backend,
      model_id: form.model.trim() || form.reranker,
    },
    mediaSearch.value,
  ),
);
const rerankerDevicePlaceholder = computed(() => {
  const configuredDevice = effectiveRerankerMedia.value
    ? modelData.value.reranker?.media_device
    : modelData.value.reranker?.device;
  return configuredDevice
    ? t("console.configuredDevicePlaceholder", { device: configuredDevice })
    : t("console.engineDefault");
});
const rerankerModelPlaceholder = computed(
  () =>
    form.reranker ||
    defaultRerankerModel.value ||
    t("console.rerankerModelExample"),
);
const excludedIds = computed(() =>
  form.excluded.split(/[\s,]+/).filter(Boolean),
);
const excludeChunk = (id: string) => {
  form.excluded = [...new Set([...excludedIds.value, id])].join("\n");
};
const retrieve = async (query: string, signal?: AbortSignal) => {
  if (!query.trim() || !form.modalities.length)
    throw new Error(t("console.required"));
  const documents = form.modalities.includes("document");
  const data: RetrieveRequest = {
    query: query.trim(),
    libraries: [props.libraryData.name],
    asset_pool_ids: form.pool ? [form.pool] : [],
    top_k: form.topK,
    include_graph_trace: documents && ["rrf", "graph"].includes(form.type),
    target_media: form.modalities.length === 4 ? [] : form.modalities,
    exclude_chunk_ids: excludedIds.value,
  };
  if (documents) data.retriever_type = form.type;
  if (form.reranker !== "__none__") {
    data.postprocess = { processor_type: "reranker", top_n: form.topN };
    if (form.rerankQuery.trim())
      data.postprocess.query = form.rerankQuery.trim();
    const model = Object.fromEntries(
      Object.entries({
        model_id: form.model.trim() || form.reranker,
        backend: form.backend,
        device: form.device.trim(),
        api_base: form.apiBase.trim(),
      }).filter(([, value]) => value),
    );
    if (Object.keys(model).length) {
      data.postprocess.reranker_model = model;
    }
  }
  return requestRetrieval(data, signal);
};
const queryModelDevices = async () => {
  devicesLoading.value = true;
  try {
    deviceList.value = await getModelDevices();
  } catch (error) {
    console.error(error);
  } finally {
    devicesLoading.value = false;
  }
};
onMounted(async () => {
  modelData.value = await getModelList();
  queryModelDevices();
});

defineExpose({ retrieve, excludeChunk, excludedIds });
</script>
<style scoped lang="less">
.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--font-main-color);
  font-weight: 600;
  margin: 4px 0 20px;
  font-size: 13px;
  span {
    font-size: 10px;
    color: var(--color-primary-second);
    background: var(--bg-card-color);
    border-radius: 4px;
    padding: 3px 5px;
  }
}
.modality-options {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px 0;
  width: 100%;
  .intel-checkbox-wrapper {
    margin: 0;
  }
}
.slider-wrap {
  display: flex;
  gap: 16px;
  align-items: center;
  .intel-slider {
    flex: 1;
    margin: 10px 2px;
  }
  .intel-input-number {
    width: 65px;
  }
}
.advanced-wrap {
  border-top: 1px solid var(--border-main-color);
  :deep(.intel-collapse-header) {
    padding: 16px 0;
  }
  :deep(.intel-collapse-content-box) {
    padding: 0;
  }
}
.retrieval-form :deep(.intel-form-item-label > label) {
  font-size: 12px;
  color: var(--font-text-color);
}
</style>
