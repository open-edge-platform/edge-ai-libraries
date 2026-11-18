<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-modal
    v-model:open="modelVisible"
    :title="$t(isEdit ? 'console.editDatabase' : 'console.registerDatabase')"
    width="700px"
    centered
    :maskClosable="false"
    @cancel="handleClose"
  >
    <div :aria-busy="loading">
      <a-form
        ref="formRef"
        :model="form"
        :rules="rules"
        layout="vertical"
        autocomplete="off"
        class="form-wrap"
        @finish="handleSubmit"
      >
        <div class="section-title">
          <DatabaseOutlined />
          {{ $t("console.basicInformation") }}
        </div>
        <a-form-item :label="$t('console.id')" name="id">
          <a-input
            v-model:value="form.id"
            :disabled="isEdit"
            placeholder="milvus_main"
          />
        </a-form-item>
        <a-row :gutter="20">
          <a-col :span="12">
            <a-form-item :label="$t('console.type')" name="type">
              <a-select
                :value="form.type || undefined"
                :placeholder="$t('console.pleaseSelect')"
                :disabled="isEdit"
                :options="
                  backendList.map((item) => ({
                    value: item.database_type,
                    label: item.database_type,
                  }))
                "
                @change="handleTypeChange"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="$t('console.backend')" name="backend">
              <a-select
                :value="form.backend || undefined"
                :placeholder="$t('console.pleaseSelect')"
                :options="backendOptions"
                @change="handleBackendChange"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <div class="section-title">
          <CodeOutlined />
          {{ $t("console.connectionOptions") }}
          <FormTooltip :title="$t('console.databaseOptionsHint')" />
        </div>
        <a-form-item name="options">
          <a-textarea
            v-model:value="form.options"
            :rows="7"
            placeholder='{"uri": "http://milvus-standalone:19530"}'
            class="json-input"
          />
        </a-form-item>
        <a-alert
          type="info"
          showIcon
          :message="$t('console.credentialsHint')"
          class="notice-wrap"
        />
        <a-form-item :label="$t('console.description')">
          <a-input
            v-model:value="form.description"
            :placeholder="$t('console.databaseDescriptionExample')"
          />
        </a-form-item>
      </a-form>
    </div>
    <template #footer>
      <a-button @click="handleClose">{{ $t("common.cancel") }}</a-button>
      <a-button type="primary" :loading="submitLoading" @click="handleSubmit">
        {{ $t("common.save") }}
      </a-button>
    </template>
  </a-modal>
</template>
<script lang="ts" setup name="UpdateDialog">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import type { FormInstance } from "ant-design-vue";
import { CodeOutlined, DatabaseOutlined } from "@ant-design/icons-vue";
import FormTooltip from "@/components/FormTooltip.vue";
import {
  getDatabaseBackendList,
  requestDatabaseCreate,
  requestDatabaseUpdate,
} from "@/api/console";
import type { BackendOption, Database, JsonObject } from "@/api/console/type";
const props = defineProps<{ dialogData?: Database }>();
const emit = defineEmits<{ close: []; search: [] }>();
const handleClose = () => emit("close");
const handleTypeChange = (value: unknown) => {
  form.type = String(value);
  form.backend = "";
};
const handleBackendChange = (value: unknown) => {
  form.backend = String(value);
};
const { t } = useI18n();
const modelVisible = ref(true);
const loading = ref(false);
const submitLoading = ref(false);
const formRef = ref<FormInstance>();
const isEdit = computed(() => !!props.dialogData);
const backendList = ref<BackendOption[]>([]);
const form = reactive({
  id: props.dialogData?.id || "",
  type: props.dialogData?.type || "",
  backend: props.dialogData?.backend || "",
  options: props.dialogData
    ? JSON.stringify(props.dialogData.options, null, 2)
    : '{"uri": "http://milvus-standalone:19530"}',
  description: props.dialogData?.description || "",
});
const backendOptions = computed(
  () =>
    backendList.value
      .find((item) => item.database_type === form.type)
      ?.backends.map((value) => ({ value, label: value })) || [],
);
const rules = computed(() => ({
  id: [{ required: true, whitespace: true, message: t("console.required") }],
  type: [{ required: true, message: t("console.required") }],
  backend: [{ required: true, message: t("console.required") }],
  options: [
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
const queryBackendList = async () => {
  loading.value = true;
  try {
    backendList.value = await getDatabaseBackendList();
  } finally {
    loading.value = false;
  }
};
const handleSubmit = async () => {
  try {
    await formRef.value!.validate();
  } catch {
    return;
  }
  submitLoading.value = true;
  try {
    const data = {
      backend: form.backend,
      options: JSON.parse(form.options || "{}") as JsonObject,
      description: form.description.trim(),
    };
    if (isEdit.value) await requestDatabaseUpdate(form.id, data);
    else
      await requestDatabaseCreate({
        ...data,
        id: form.id.trim(),
        type: form.type,
      });
    emit("search");
    emit("close");
  } finally {
    submitLoading.value = false;
  }
};
onMounted(queryBackendList);
</script>
<style scoped lang="less">
.form-wrap {
  padding: 16px 0 4px;
}
.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0 18px;
  color: var(--font-main-color);
  font-weight: 600;
  .anticon {
    color: var(--color-primary-second);
  }
}
.json-input {
  font-family: monospace;
  font-size: 13px;
  line-height: 1.8;
}
.notice-wrap {
  margin: 0 0 24px;
  font-size: 12px;
}
</style>
