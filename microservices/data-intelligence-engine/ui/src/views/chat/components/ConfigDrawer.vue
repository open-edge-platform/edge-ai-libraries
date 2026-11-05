<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-drawer
    :open="open"
    :title="$t('console.configuration')"
    width="min(500px, 100vw)"
    forceRender
    @close="handleClose"
  >
    <div class="module-wrap">
      <div class="module-title">
        <ApiOutlined />
        {{ $t("console.chatEndpoint") }}
      </div>
      <a-form
        ref="formRef"
        :model="form"
        :rules="rules"
        layout="vertical"
        autocomplete="off"
      >
        <a-form-item :label="$t('console.endpoint')" name="endpoint" required>
          <a-input
            v-model:value="form.endpoint"
            placeholder="http://localhost:8000/v1"
          />
        </a-form-item>
        <a-form-item :label="$t('console.modelId')" name="model" required>
          <div class="model-input">
            <a-auto-complete
              v-model:value="form.model"
              :placeholder="$t('console.chatModelPlaceholder')"
              :options="modelList.map((value) => ({ value }))"
            />
            <a-tooltip :title="$t('console.loadModels')">
              <a-button
                :loading="loading"
                :aria-label="$t('console.loadModels')"
                @click="handleLoadModels"
              >
                <template #icon><ReloadOutlined /></template>
              </a-button>
            </a-tooltip>
          </div>
        </a-form-item>
        <a-form-item :label="$t('console.apiKey')">
          <a-input-password
            v-model:value="form.apiKey"
            autocomplete="off"
            placeholder="sk-..."
          />
        </a-form-item>
      </a-form>
      <p class="module-hint">
        <InfoCircleOutlined />
        {{ $t("console.chatNotice") }}
      </p>
      <a-alert
        v-if="errorMessage"
        type="error"
        showIcon
        :message="errorMessage"
        class="notice-wrap"
      />
    </div>
    <div class="module-wrap">
      <div class="module-title">
        <SlidersOutlined />
        {{ $t("console.retrievalSettings") }}
      </div>
      <RetrievalForm ref="retrievalRef" :library-data="libraryData" />
    </div>
    <template #footer>
      <a-button type="primary" @click="handleConfirm">
        {{ $t("common.confirm") }}
      </a-button>
    </template>
  </a-drawer>
</template>
<script lang="ts" setup name="ConfigDrawer">
import { computed, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import type { FormInstance } from "ant-design-vue";
import {
  ApiOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  SlidersOutlined,
} from "@ant-design/icons-vue";
import type { Library } from "@/api/console/type";
import { Local, Session } from "@/utils/storage";
import RetrievalForm from "../../retrieve/components/RetrievalForm.vue";
defineProps<{ open: boolean; libraryData: Library }>();
const emit = defineEmits<{ close: [] }>();
const handleClose = () => emit("close");
const handleLoadModels = () => queryModelList();
const { t } = useI18n();
const formRef = ref<FormInstance>();
const retrievalRef = ref<InstanceType<typeof RetrievalForm>>();
const loading = ref(false);
const errorMessage = ref("");
const modelList = ref<string[]>([]);
const form = reactive({
  endpoint: String(Local.get("console.chat.endpoint") || ""),
  model: String(Local.get("console.chat.model") || ""),
  apiKey: String(Session.get("console.chat.key") || ""),
});
const normalizeEndpoint = (value: string) => {
  const base = value
    .trim()
    .replace(/\/+$/, "")
    .replace(/\/chat\/completions$/, "");
  const url = new URL(base);
  if (!["http:", "https:"].includes(url.protocol))
    throw new Error(t("console.invalidUrl"));
  return base;
};
const rules = computed(() => ({
  endpoint: [
    { required: true, whitespace: true, message: t("console.required") },
    {
      validator: async (_rule: unknown, value: string) => {
        if (!value?.trim()) return;
        normalizeEndpoint(value);
      },
    },
  ],
  model: [{ required: true, whitespace: true, message: t("console.required") }],
}));
const excludedIds = computed(() => retrievalRef.value?.excludedIds || []);
const handleConfirm = async () => {
  try {
    await formRef.value!.validate();
  } catch {
    return;
  }
  emit("close");
};
const queryModelList = async () => {
  errorMessage.value = "";
  loading.value = true;
  try {
    const base = normalizeEndpoint(form.endpoint);
    const headers: Record<string, string> = {};
    if (form.apiKey.trim())
      headers.Authorization = `Bearer ${form.apiKey.trim()}`;
    const response = await fetch(`${base}/models`, { headers });
    if (!response.ok)
      throw new Error(`${response.status}: ${await response.text()}`);
    const data: { data: { id: string }[] } = await response.json();
    modelList.value = data.data.map((item) => item.id);
    if (!modelList.value.length) errorMessage.value = t("console.noModels");
    else if (!form.model) form.model = modelList.value[0];
  } catch (error) {
    errorMessage.value =
      error instanceof TypeError
        ? t("console.chatNetworkError")
        : error instanceof Error
          ? error.message
          : String(error);
  } finally {
    loading.value = false;
  }
};
const retrieve = (query: string, signal?: AbortSignal) =>
  retrievalRef.value!.retrieve(query, signal);
const excludeChunk = (id: string) => retrievalRef.value?.excludeChunk(id);
watch(
  () => form.endpoint,
  (value) => Local.set("console.chat.endpoint", value),
);
watch(
  () => form.model,
  (value) => Local.set("console.chat.model", value),
);
watch(
  () => form.apiKey,
  (value) => Session.set("console.chat.key", value),
);
defineExpose({ form, retrieve, excludeChunk, excludedIds });
</script>
<style scoped lang="less">
.module-wrap {
  border: 1px solid var(--border-main-color);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}
.module-title {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
  color: var(--font-main-color);
  margin-bottom: 20px;
  .anticon {
    color: var(--color-primary-second);
  }
}
.model-input {
  display: flex;
  gap: 10px;
  .intel-select {
    flex: 1;
  }
}
.module-hint {
  display: flex;
  gap: 8px;
  color: var(--font-info-color);
  font-size: 12px;
  line-height: 1.8;
  .anticon {
    margin-top: 5px;
    flex-shrink: 0;
  }
}
.notice-wrap {
  margin-top: 16px;
}
</style>
