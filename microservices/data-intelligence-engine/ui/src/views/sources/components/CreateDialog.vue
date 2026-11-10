<!-- Copyright (C) 2026 Intel Corporation; SPDX-License-Identifier: Apache-2.0 -->
<template>
  <a-modal
    v-model:open="modelVisible"
    :title="$t('console.createSource')"
    width="820px"
    centered
    :maskClosable="false"
    @cancel="handleClose"
  >
    <div :aria-busy="loading">
      <div class="dialog-body">
        <a-steps :current="currentStep" size="small" class="steps-wrap">
          <a-step :title="$t('console.basicInformation')" />
          <a-step :title="$t('console.sourceConfiguration')" />
        </a-steps>
        <a-form
          ref="formRef"
          :model="form"
          :rules="rules"
          layout="vertical"
          autocomplete="off"
          @finish="handleNext"
        >
          <div v-show="currentStep === 0" class="basic-section">
            <a-alert
              v-if="!databaseList.length"
              type="info"
              showIcon
              :message="$t('console.databaseFirst')"
              class="notice-wrap"
            />
            <a-form-item :label="$t('console.name')" name="name">
              <a-input v-model:value="form.name" placeholder="docs_vectors" />
            </a-form-item>
            <a-form-item :label="$t('console.database')" name="database_id">
              <a-select
                :value="form.database_id || undefined"
                :placeholder="$t('console.pleaseSelect')"
                :options="
                  databaseList.map((item) => ({
                    value: item.id,
                    label: `${item.id} (${item.type}/${item.backend})`,
                  }))
                "
                @change="handleDatabaseChange"
              />
            </a-form-item>
            <a-form-item>
              <template #label>
                {{ $t("console.collection") }}
                <FormTooltip :title="$t('console.collectionHint')" />
              </template>
              <a-input
                v-model:value="form.collection_name"
                placeholder="documents"
              />
            </a-form-item>
          </div>
          <div v-if="currentStep === 1">
            <div class="configuration-title">
              <DeploymentUnitOutlined />
              <strong>{{ form.name }}</strong>
              <a-tag class="theme-tag-primary" :bordered="false">
                {{ $t(`console.${databaseType}Source`) }}
              </a-tag>
              <span>{{ form.database_id }}</span>
            </div>
            <SourceOptions
              v-model="options"
              :type="databaseType"
              :model-data="modelData"
            />
            <a-alert
              v-if="validationError"
              type="error"
              showIcon
              :message="validationError"
              class="notice-wrap"
            />
          </div>
        </a-form>
      </div>
    </div>
    <template #footer>
      <div class="footer-wrap">
        <a-button v-if="currentStep" @click="handlePrevious">
          {{ $t("common.prev") }}
        </a-button>
        <span v-else />
        <div>
          <a-button @click="handleClose">{{ $t("common.cancel") }}</a-button>
          <a-button v-if="currentStep === 0" type="primary" @click="handleNext">
            {{ $t("common.next") }}
          </a-button>
          <a-button
            v-else
            type="primary"
            :loading="submitLoading"
            @click="handleSubmit"
          >
            {{ $t("console.createSource") }}
          </a-button>
        </div>
      </div>
    </template>
  </a-modal>
</template>
<script lang="ts" setup name="CreateDialog">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import type { FormInstance } from "ant-design-vue";
import { DeploymentUnitOutlined } from "@ant-design/icons-vue";
import FormTooltip from "@/components/FormTooltip.vue";
import {
  getDatabaseList,
  getModelList,
  requestSourceCreate,
} from "@/api/console";
import type {
  Database,
  JsonObject,
  Library,
  ModelOptions,
  Source,
} from "@/api/console/type";
import SourceOptions from "./SourceOptions.vue";
import {
  serializeSourceOptions,
  sourceOptionsDefaults,
} from "../SourceOptions";
const props = defineProps<{ libraryData: Library }>();
const emit = defineEmits<{ close: []; search: []; created: [id: string, source: Source] }>();
const handleClose = () => emit("close");
const handleDatabaseChange = (value: unknown) => {
  form.database_id = String(value);
};
const handlePrevious = () => {
  currentStep.value = 0;
};
const { t } = useI18n();
const modelVisible = ref(true);
const loading = ref(false);
const submitLoading = ref(false);
const currentStep = ref(0);
const validationError = ref("");
const formRef = ref<FormInstance>();
const form = reactive({ name: "", database_id: "", collection_name: "" });
const options = ref(sourceOptionsDefaults());
const databaseList = ref<Database[]>([]);
const modelData = ref<Record<string, ModelOptions>>({});
const databaseType = computed(
  () =>
    databaseList.value.find((item) => item.id === form.database_id)?.type || "",
);
const rules = computed(() => ({
  name: [{ required: true, whitespace: true, message: t("console.required") }],
  database_id: [{ required: true, message: t("console.required") }],
}));
const queryConfiguration = async () => {
  loading.value = true;
  try {
    [databaseList.value, modelData.value] = await Promise.all([
      getDatabaseList(),
      getModelList(),
    ]);
  } finally {
    loading.value = false;
  }
};
const handleNext = async () => {
  try {
    await formRef.value!.validate();
  } catch {
    return;
  }
  currentStep.value = 1;
};
const handleSubmit = async () => {
  validationError.value = "";
  let operatorOptions: JsonObject;
  try {
    operatorOptions = serializeSourceOptions(
      databaseType.value,
      options.value,
      t,
      modelData.value,
    );
  } catch (error) {
    validationError.value =
      error instanceof Error ? error.message : String(error);
    return;
  }
  submitLoading.value = true;
  try {
    const data = await requestSourceCreate(props.libraryData.name, {
      name: form.name.trim(),
      database_id: form.database_id,
      collection_name: form.collection_name.trim() || undefined,
      operator_options: operatorOptions,
    });
    emit("search");
    emit("created", data.id, data);
    emit("close");
  } finally {
    submitLoading.value = false;
  }
};
onMounted(queryConfiguration);
</script>
<style scoped lang="less">
.dialog-body {
  padding: 20px 0 8px;
}
.steps-wrap {
  margin-bottom: 28px;
}
.basic-section {
  max-width: 560px;
  margin: 0 auto;
  padding: 4px 0 12px;
}
.configuration-title {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 6px;
  background: var(--bg-card-color);
  margin-bottom: 22px;
  color: var(--font-main-color);
  .anticon {
    color: var(--color-primary-second);
    font-size: 18px;
  }
  > span:last-child {
    color: var(--font-info-color);
    font-size: 12px;
    margin-left: auto;
  }
}
.notice-wrap {
  margin: 16px 0;
}
.footer-wrap {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
