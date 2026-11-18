<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-modal
    v-model:open="modelVisible"
    :title="$t('console.createPool')"
    width="640px"
    centered
    wrap-class-name="create-pool-modal"
    :maskClosable="false"
    @cancel="handleClose"
  >
    <div class="dialog-body">
      <a-form
        ref="formRef"
        :model="form"
        :rules="rules"
        layout="vertical"
        autocomplete="off"
        @finish="handleSubmit"
      >
        <div class="section-title">
          <span>01</span>
          {{ $t("console.basicInformation") }}
        </div>
        <a-row :gutter="20">
          <a-col :span="12">
            <a-form-item :label="$t('console.id')" name="id">
              <a-input v-model:value="form.id" placeholder="documents" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="$t('console.name')" name="name">
              <a-input
                v-model:value="form.name"
                :placeholder="$t('console.poolNameExample')"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <div class="section-title">
          <span>02</span>
          {{ $t("console.sources") }}
          <FormTooltip :title="$t('console.poolSourcesHint')" />
        </div>
        <a-alert
          v-if="!sourceList.length"
          type="info"
          showIcon
          :message="$t('console.sourcesFirst')"
          class="notice-wrap"
        />
        <a-form-item name="sources">
          <a-checkbox-group v-model:value="form.sources" class="source-options">
            <label
              v-for="source in sourceList"
              :key="source.id"
              class="source-option"
              :class="{ selected: form.sources.includes(source.id) }"
            >
              <a-checkbox :value="source.id" />
              <div>
                <strong>{{ source.name }}</strong>
                <p>{{ source.database_id }} / {{ source.collection_name }}</p>
              </div>
              <a-tag :bordered="false">{{ source.type }}</a-tag>
            </label>
          </a-checkbox-group>
        </a-form-item>
        <a-form-item name="metadata">
          <template #label>
            {{ $t("console.metadata") }}
            <FormTooltip :title="$t('console.metadataHint')" />
          </template>
          <a-textarea
            v-model:value="form.metadata"
            :rows="3"
            placeholder='{"owner": "team-a"}'
          />
        </a-form-item>
      </a-form>
    </div>
    <template #footer>
      <a-button @click="handleClose">{{ $t("common.cancel") }}</a-button>
      <a-button type="primary" :loading="submitLoading" @click="handleSubmit">
        {{ $t("console.createPool") }}
      </a-button>
    </template>
  </a-modal>
</template>
<script lang="ts" setup name="CreateDialog">
import { computed, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import type { FormInstance } from "ant-design-vue";
import { requestAssetPoolCreate } from "@/api/console";
import type { JsonObject, Library } from "@/api/console/type";
import FormTooltip from "@/components/FormTooltip.vue";
const props = defineProps<{
  libraryData: Library;
  initialSources?: string[];
}>();
const emit = defineEmits<{ close: []; search: []; created: [id: string] }>();
const handleClose = () => emit("close");
const { t } = useI18n();
const modelVisible = ref(true);
const submitLoading = ref(false);
const formRef = ref<FormInstance>();
const form = reactive({
  id: "",
  name: "",
  sources: [...(props.initialSources || [])],
  metadata: "",
});
const sourceList = computed(() =>
  props.libraryData.sources.filter((source) => source.type !== "object"),
);
const rules = computed(() => ({
  id: [{ required: true, whitespace: true, message: t("console.required") }],
  sources: [
    {
      required: true,
      type: "array" as const,
      min: 1,
      message: t("console.sourceRequired"),
    },
  ],
  metadata: [
    {
      validator: async (_rule: unknown, value: string) => {
        let data: unknown;
        try {
          data = JSON.parse(value || "{}");
        } catch {
          throw new Error(t("console.invalidJson"));
        }
        if (!data || typeof data !== "object" || Array.isArray(data))
          throw new Error(t("console.invalidJson"));
      },
    },
  ],
}));
const handleSubmit = async () => {
  try {
    await formRef.value!.validate();
  } catch {
    return;
  }
  submitLoading.value = true;
  try {
    const data = await requestAssetPoolCreate(props.libraryData.name, {
      id: form.id.trim(),
      name: form.name.trim() || form.id.trim(),
      sources: form.sources,
      metadata: JSON.parse(form.metadata || "{}") as JsonObject,
    });
    emit("search");
    emit("created", data.id);
    emit("close");
  } finally {
    submitLoading.value = false;
  }
};
</script>
<style scoped lang="less">
:global(.create-pool-modal .intel-modal-content) {
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 32px);
  max-height: calc(100dvh - 32px);
}
:global(.create-pool-modal .intel-modal-body) {
  min-height: 0;
  overflow-y: auto;
}
:global(.create-pool-modal .intel-modal-header),
:global(.create-pool-modal .intel-modal-footer) {
  flex-shrink: 0;
}
.dialog-body {
  padding: 16px 0 4px;
}
.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  color: var(--font-main-color);
  margin-bottom: 20px;
  span {
    font-size: 11px;
    color: var(--color-primary-second);
    border-radius: 4px;
    background: var(--bg-card-color);
    padding: 4px 6px;
  }
}
.source-options {
  display: flex;
  flex-direction: column;
  width: 100%;
  gap: 10px;
}
.source-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-main-color);
  border-radius: 6px;
  cursor: pointer;
  &.selected {
    border-color: var(--color-primary-second);
    background: color-mix(in srgb, var(--color-primary-second) 4%, transparent);
  }
  > div {
    flex: 1;
  }
  strong {
    font-weight: 500;
    color: var(--font-main-color);
  }
  p {
    font-size: 12px;
    color: var(--font-info-color);
    margin-top: 5px;
  }
}
.notice-wrap {
  margin-bottom: 16px;
}
</style>
