<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <template v-if="type === 'vector'">
    <a-form-item>
      <template #label>
        {{ $t("console.contentTypes") }}
        <FormTooltip :title="$t('console.vectorHint') + ' ' + $t(`console.${mode}EmbeddingHint`)" />
      </template>
      <a-checkbox-group
        v-model:value="form.vectorTypes"
        :options="
          ['document', 'image', 'video', 'audio'].map((value) => ({
            value,
            label: $t(`console.${value}`),
          }))
        "
      />
    </a-form-item>
    <div class="console-form-row">
      <a-form-item>
        <template #label>
          {{ $t("console.backend") }}
          <FormTooltip :title="$t(mode === 'document' ? 'console.documentBackendHint' : 'console.mediaBackendHint')" />
        </template>
        <a-select
          v-model:value="vector.backend"
          :placeholder="$t('console.pleaseSelect')"
          :options="[
            { value: '', label: $t('console.engineDefault') },
            ...backends.map((value) => ({ value, label: value })),
          ]"
        />
      </a-form-item>
      <a-form-item>
        <template #label>
          {{ $t("console.modelId") }}
          <FormTooltip :title="$t('console.embeddingModelHint')" />
        </template>
        <a-auto-complete
          v-model:value="vector.model"
          :options="catalog?.models.map((model) => ({ value: model.name }))"
          :placeholder="catalog?.model_id || 'BAAI/bge-m3'"
        />
      </a-form-item>
    </div>
    <a-form-item v-if="vector.backend === 'openai_compatible'">
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
        :placeholder="$t('console.pleaseSelect')"
        :options="[
          { value: '', label: $t('console.engineDefault') },
          ...['CPU', 'GPU', 'GPU.0', 'AUTO'].map((value) => ({
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
        <a-form-item
          v-else-if="vector.backend !== 'openai_compatible'"
        >
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
        <FormTooltip :title="$t('console.graphHint') + ' ' + $t('console.documentExtractionHint')" />
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
        <a-input v-model:value="form.extractorUrl" placeholder="http://okf-extractor:8080" />
      </a-form-item>
      <div class="console-form-row">
        <a-form-item>
          <template #label>
            {{ $t("console.apiKey") }}
            <FormTooltip :title="$t('console.extractorApiKeyHint')" />
          </template>
          <a-input-password v-model:value="form.apiKey" autocomplete="off" placeholder="sk-..." />
        </a-form-item>
        <a-form-item>
          <template #label>
            {{ $t("console.timeout") }}
            <FormTooltip :title="$t('console.extractorTimeoutHint')" />
          </template>
          <a-input-number v-model:value="form.timeout" :min="1" placeholder="3600" />
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
        <a-form-item
          v-if="form.trigger === 'auto'"
        >
          <template #label>
            {{ $t("console.debounce") }}
            <FormTooltip :title="$t('console.debounceHint')" />
          </template>
          <a-input-number v-model:value="form.debounce" :min="0" :max="86400" placeholder="15" />
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
        <a-input v-model:value="form.language" :maxlength="100" placeholder="en, zh, English" />
      </a-form-item>
      <a-form-item>
        <template #label>
          {{ $t("console.goal") }}
          <FormTooltip :title="$t('console.extractionTaskHint')" />
        </template>
        <a-textarea v-model:value="form.goal" :rows="3" :maxlength="8000" :placeholder="$t('console.extractionGoalExample')" />
      </a-form-item>
      <a-collapse ghost>
        <a-collapse-panel
          key="instructions"
          :header="$t('console.instructions')"
        >
          <a-form-item
            v-for="key in instructionKeys"
            :key="key"
          >
            <template #label>
              {{ $t(`console.${key}`) }}
              <FormTooltip :title="$t(`console.${key}Hint`)" />
            </template>
            <a-textarea v-model:value="form.instructions[key]" :rows="2" :placeholder="$t(`console.${key}Example`)" />
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
import { computed } from "vue";
import FormTooltip from "@/components/FormTooltip.vue";
import type { ModelOptions } from "@/api/console/type";
import { instructionKeys, vectorMode } from "../SourceOptions";
import type { SourceOptionsForm } from "../SourceOptions";
const props = defineProps<{
  type: string;
  modelData: Record<string, ModelOptions>;
}>();
const form = defineModel<SourceOptionsForm>({ required: true });
const mode = computed(() => vectorMode(form.value.vectorTypes));
const vector = computed(() => form.value.vectors[mode.value]);
const catalog = computed(
  () => props.modelData[mode.value === "document" ? "embedding" : "multimodal"],
);
const backends = computed(() =>
  mode.value === "document"
    ? [
        "llamaindex_openvino",
        "openvino_genai",
        "openai_compatible",
        "native_openvino_gme",
      ]
    : ["llamaindex_openvino"],
);
</script>
<style scoped lang="less">
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
