<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <template v-if="type === 'vector'">
    <a-form-item>
      <template #label>
        {{ $t("console.contentTypes") }}
        <a-tooltip placement="top" arrow-point-at-center>
          <template #title>
            <ul class="content-rules">
              <li>{{ $t("console.vectorRuleDocumentMedia") }}</li>
              <li>{{ $t("console.vectorRuleVideo") }}</li>
            </ul>
          </template>
          <InfoCircleOutlined class="content-rules-icon" />
        </a-tooltip>
      </template>
      <a-checkbox-group
        :value="form.vectorTypes"
        :options="
          ['document', 'audio', 'image', 'video'].map((value) => ({
            value,
            label: $t(`console.${value}`),
          }))
        "
        @change="handleVectorTypesChange"
      />
    </a-form-item>
    <div class="console-form-row">
      <a-form-item>
        <template #label>
          {{ $t("console.backend") }}
          <FormTooltip
            :title="
              $t(
                mode === 'document'
                  ? 'console.documentBackendHint'
                  : 'console.mediaBackendHint',
              )
            "
          />
        </template>
        <a-select
          v-model:value="vector.backend"
          :placeholder="$t('console.pleaseSelect')"
          :options="[
            { value: '', label: engineDefaultLabel('backend') },
            ...backends.map((value) => ({ value, label: value })),
          ]"
          @change="handleBackendChange"
        />
      </a-form-item>
      <a-form-item :required="modelRequired">
        <template #label>
          {{ $t("console.modelId") }}
          <FormTooltip :title="$t('console.embeddingModelHint')" />
        </template>
        <a-auto-complete
          v-if="remote"
          v-model:value="vector.model"
          :disabled="!vector.backend"
          :options="remoteModels"
          :placeholder="
            vector.backend
              ? $t('console.pleaseSelect')
              : engineDefaultLabel('model_id')
          "
        />
        <a-select
          v-else
          :value="selectValue"
          :options="modelOptions"
          :disabled="choice.status === 'none'"
          :placeholder="modelPlaceholder"
          @update:value="(value?: string) => (vector.model = value ?? '')"
        />
      </a-form-item>
    </div>
    <a-form-item v-if="vector.backend === 'remote_openai_compatible'">
      <template #label>
        {{ $t("console.apiBase") }}
        <FormTooltip :title="$t('console.embeddingApiHint')" />
      </template>
      <a-input
        v-model:value="vector.apiBase"
        placeholder="http://host:port/v1"
      />
    </a-form-item>
    <a-form-item v-else>
      <template #label>
        {{ $t("console.device") }}
        <FormTooltip :title="$t('console.inheritEngineHint')" />
      </template>
      <a-select
        v-model:value="vector.device"
        :loading="devicesLoading"
        :placeholder="$t('console.pleaseSelect')"
        :options="[
          { value: '', label: engineDefaultLabel('device') },
          ...deviceList.map((value) => ({
            value,
            label: value,
          })),
        ]"
      />
    </a-form-item>
    <a-collapse ghost>
      <a-collapse-panel key="advanced" :header="$t('console.advanced')">
        <div v-if="mode === 'document'" class="console-form-row">
          <a-form-item>
            <template #label>
              {{ $t("console.chunkSize") }}
              <FormTooltip :title="$t('console.chunkOptionsHint')" />
            </template>
            <a-input-number
              v-model:value="vector.chunkSize"
              placeholder="512"
              :min="1"
              :precision="0"
            />
          </a-form-item>
          <a-form-item>
            <template #label>
              {{ $t("console.chunkOverlap") }}
              <FormTooltip :title="$t('console.chunkOptionsHint')" />
            </template>
            <a-input-number
              v-model:value="vector.chunkOverlap"
              placeholder="50"
              :min="0"
              :precision="0"
            />
          </a-form-item>
          <a-form-item>
            <template #label>
              {{ $t("console.figureContext") }}
              <FormTooltip :title="$t('console.figureContextHint')" />
            </template>
            <a-input-number
              v-model:value="vector.figureContext"
              placeholder="200"
              :min="0"
              :precision="0"
            />
          </a-form-item>
        </div>
        <a-form-item v-if="mode === 'video'">
          <template #label>
            {{ $t("console.framesPerClip") }}
            <FormTooltip :title="$t('console.framesPerClipHint')" />
          </template>
          <a-input-number
            v-model:value="vector.framesPerClip"
            placeholder="8"
            :min="1"
            :precision="0"
          />
        </a-form-item>
        <a-form-item v-else-if="vector.backend !== 'remote_openai_compatible'">
          <template #label>
            {{ $t("console.maxImageTokens") }}
            <FormTooltip :title="$t('console.maxImageTokensHint')" />
          </template>
          <a-input-number
            v-model:value="vector.maxImageTokens"
            placeholder="1024"
            :min="1"
            :precision="0"
          />
        </a-form-item>
      </a-collapse-panel>
    </a-collapse>
  </template>
  <template v-else-if="type === 'graph'">
    <a-form-item>
      <template #label>
        {{ $t("console.contentTypes") }}
        <FormTooltip
          :title="
            $t('console.graphHint') + ' ' + $t('console.documentExtractionHint')
          "
        />
      </template>
      <a-checkbox-group
        v-model:value="form.graphTypes"
        :options="
          ['okf', 'document'].map((value) => ({
            value,
            label: $t(`console.${value}`),
          }))
        "
      />
    </a-form-item>
    <template v-if="form.graphTypes.includes('document')">
      <a-form-item>
        <template #label>
          {{ $t("console.extractorUrl") }}
          <FormTooltip :title="$t('console.extractorUrlHint')" />
        </template>
        <a-input
          v-model:value="form.extractorUrl"
          placeholder="http://okf-extractor:8080"
        />
      </a-form-item>
      <div class="console-form-row">
        <a-form-item>
          <template #label>
            {{ $t("console.apiKey") }}
            <FormTooltip :title="$t('console.extractorApiKeyHint')" />
          </template>
          <a-input-password
            v-model:value="form.apiKey"
            autocomplete="off"
            placeholder="sk-..."
          />
        </a-form-item>
        <a-form-item>
          <template #label>
            {{ $t("console.timeout") }}
            <FormTooltip :title="$t('console.extractorTimeoutHint')" />
          </template>
          <a-input-number
            v-model:value="form.timeout"
            :min="1"
            placeholder="3600"
          />
        </a-form-item>
        <a-form-item>
          <template #label>
            {{ $t("console.trigger") }}
            <FormTooltip :title="$t('console.extractionTriggerHint')" />
          </template>
          <a-select
            v-model:value="form.trigger"
            :placeholder="$t('console.pleaseSelect')"
            :options="
              ['auto', 'manual', 'schedule'].map((value) => ({
                value,
                label: $t(`console.${value}`),
              }))
            "
          />
        </a-form-item>
        <a-form-item v-if="form.trigger === 'auto'">
          <template #label>
            {{ $t("console.debounce") }}
            <FormTooltip :title="$t('console.debounceHint')" />
          </template>
          <a-input-number
            v-model:value="form.debounce"
            :min="0"
            :max="86400"
            placeholder="15"
          />
        </a-form-item>
      </div>
      <div v-if="form.trigger === 'schedule'" class="console-form-row">
        <a-form-item>
          <template #label>
            {{ $t("console.cron") }}
            <FormTooltip :title="$t('console.cronHint')" />
          </template>
          <a-input v-model:value="form.cron" placeholder="0 2 * * *" />
        </a-form-item>
        <a-form-item>
          <template #label>
            {{ $t("console.timezone") }}
            <FormTooltip :title="$t('console.timezoneHint')" />
          </template>
          <a-input v-model:value="form.timezone" placeholder="Asia/Shanghai" />
        </a-form-item>
      </div>
      <a-form-item>
        <template #label>
          {{ $t("console.language") }}
          <FormTooltip :title="$t('console.extractionTaskHint')" />
        </template>
        <a-input
          v-model:value="form.language"
          :maxlength="100"
          placeholder="en, zh, English"
        />
      </a-form-item>
      <a-form-item>
        <template #label>
          {{ $t("console.goal") }}
          <FormTooltip :title="$t('console.extractionTaskHint')" />
        </template>
        <a-textarea
          v-model:value="form.goal"
          :rows="3"
          :maxlength="8000"
          :placeholder="$t('console.extractionGoalExample')"
        />
      </a-form-item>
      <a-collapse ghost>
        <a-collapse-panel
          key="instructions"
          :header="$t('console.instructions')"
        >
          <a-form-item v-for="key in instructionKeys" :key="key">
            <template #label>
              {{ $t(`console.${key}`) }}
              <FormTooltip :title="$t(`console.${key}Hint`)" />
            </template>
            <a-textarea
              v-model:value="form.instructions[key]"
              :rows="2"
              :placeholder="$t(`console.${key}Example`)"
            />
          </a-form-item>
        </a-collapse-panel>
      </a-collapse>
    </template>
  </template>
  <a-alert
    v-else-if="type === 'object'"
    type="info"
    showIcon
    :message="$t('console.contentHint')"
  />
  <a-alert
    v-else-if="type === 'sql'"
    type="info"
    showIcon
    :message="$t('console.noSourceOptionsHint')"
  />
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import FormTooltip from "@/components/FormTooltip.vue";
import { getModelDevices } from "@/api/console";
import type { ModelOptions } from "@/api/console/type";
import { instructionKeys, vectorMode } from "../SourceOptions";
import {
  REMOTE_BACKEND,
  backendChoices,
  effectiveBackend,
  embeddingChoice,
  inheritedDefault,
} from "../embeddingModels";
import { useI18n } from "vue-i18n";
import { InfoCircleOutlined } from "@ant-design/icons-vue";
import type { SourceOptionsForm } from "../SourceOptions";
const props = defineProps<{
  type: string;
  modelData: Record<string, ModelOptions>;
}>();
const { t } = useI18n();
const form = defineModel<SourceOptionsForm>({ required: true });
const handleBackendChange = () => {
  vector.value.model = "";
};
const engineDefaultLabel = (field: "backend" | "device" | "model_id") => {
  const value = inheritedDefault(
    props.modelData.embedding,
    form.value.vectorTypes,
    field,
  );
  return value
    ? `${t("console.engineDefault")} (${value})`
    : t("console.engineDefault");
};
const choice = computed(() =>
  embeddingChoice(props.modelData.embedding, form.value.vectorTypes),
);
const remote = computed(
  () =>
    effectiveBackend(
      props.modelData.embedding,
      form.value.vectorTypes,
      vector.value.backend,
    ) === REMOTE_BACKEND,
);
const modelRequired = computed(() =>
  remote.value ? !!vector.value.backend : choice.value.status === "differ",
);
const modelOptions = computed(() => [
  ...(choice.value.status === "default"
    ? [
        {
          value: "",
          label: t("console.defaultModelOption", {
            model: choice.value.defaultModel,
          }),
        },
      ]
    : []),
  ...choice.value.candidates
    .filter((name) => name !== choice.value.defaultModel)
    .map((name) => ({ value: name, label: name })),
]);
const selectValue = computed(() =>
  vector.value.model || (choice.value.status === "default" ? "" : undefined),
);
const modelPlaceholder = computed(() =>
  choice.value.status === "none"
    ? t("console.noCommonModel")
    : choice.value.status === "differ"
      ? t("console.defaultModelsDiffer")
      : t("console.pleaseSelect"),
);
const remoteModels = computed(() =>
  (props.modelData.embedding?.models || [])
    .filter((model) => /^https?:/i.test(model.path || ""))
    .map((model) => ({ value: model.name })),
);
// Documents and media, and video and anything else, cannot share a source:
// the type just ticked wins and displaces the ones it cannot be combined with.
const handleVectorTypesChange = (values: Array<string | number | boolean>) => {
  const selected = values.map(String);
  const added = selected.find((value) => !form.value.vectorTypes.includes(value));
  form.value.vectorTypes =
    added === "video" || added === "document"
      ? [added]
      : added
        ? selected.filter((value) => value !== "document" && value !== "video")
        : selected;
};
const deviceList = ref<string[]>([]);
const devicesLoading = ref(false);

const mode = computed(() => vectorMode(form.value.vectorTypes));
const vector = computed(() => form.value.vectors[mode.value]);
const backends = computed(() => backendChoices(form.value.vectorTypes));
// A model chosen for one set of content types may not fit another.
watch(
  () => [...form.value.vectorTypes],
  () => {
    const model = vector.value.model;
    if (model && !remote.value && !choice.value.candidates.includes(model))
      vector.value.model = "";
  },
);

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
  queryModelDevices();
});
</script>
<style scoped lang="less">
.content-rules {
  margin: 0;
  padding-inline-start: 16px;
}
.content-rules-icon {
  margin-inline-start: 6px;
  font-size: 14px;
  color: var(--font-text-color);
}
.console-form-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 20px;
}
:deep(.intel-input-number) {
  width: 100%;
}
:deep(.intel-form-item-label .anticon) {
  margin-inline-start: 6px;
}
:deep(.intel-form-item-extra),
:deep(.intel-form-item-explain) {
  font-size: 12px;
}
:deep(.intel-collapse) {
  margin: 16px 0;
  border: 1px solid var(--border-main-color);
  border-radius: 6px;
  background: var(--bg-card-color);
}
@media (max-width: 600px) {
  .console-form-row {
    grid-template-columns: 1fr;
  }
}
</style>
