<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <a-modal
    :open="true"
    :title="dialogTitle"
    centered
    destroyOnClose
    :keyboard="false"
    :maskClosable="false"
    :confirm-loading="submitting"
    :ok-text="t('common.save')"
    :cancel-text="t('common.cancel')"
    width="640px"
    class="router-provider-form-dialog"
    @ok="handleSubmit"
    @cancel="emit('close')"
  >
    <div class="router-provider-form-scroll">
      <a-form
        ref="formRef"
        :model="formModel"
        :rules="rules"
        layout="vertical"
        class="router-provider-form"
      >
        <a-form-item :label="t('router.routerProviderName')" name="name">
          <a-input
            v-model:value="formModel.name"
            :disabled="isEdit"
            :placeholder="t('router.routerProviderNamePlaceholder')"
          />
        </a-form-item>
        <a-form-item :label="t('router.routerProviderType')" name="type">
          <a-input
            v-model:value="formModel.type"
            :placeholder="t('router.routerProviderTypePlaceholder')"
          />
        </a-form-item>
        <a-form-item :label="t('router.routerProviderModel')" name="model">
          <a-input
            v-model:value="formModel.model"
            :placeholder="t('router.routerProviderModelPlaceholder')"
          />
        </a-form-item>
        <a-form-item :label="t('router.routerProviderEnabled')" name="enabled">
          <a-radio-group v-model:value="formModel.enabled" button-style="solid">
            <a-radio :value="true">{{ t("common.yes") }}</a-radio>
            <a-radio :value="false">{{ t("common.no") }}</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item
          :label="t('router.routerProviderMetadata')"
          name="metadataText"
        >
          <a-textarea
            v-model:value="formModel.metadataText"
            :rows="4"
            :placeholder="t('router.routerProviderJsonPlaceholder')"
          />
        </a-form-item>
        <a-form-item
          :label="t('router.routerProviderSettings')"
          name="settingsText"
        >
          <a-textarea
            v-model:value="formModel.settingsText"
            :rows="4"
            :placeholder="t('router.routerProviderJsonPlaceholder')"
          />
        </a-form-item>
      </a-form>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { updateRouterProvider } from "@/api/router";
import { formatJsonText, parseJsonText } from "@/utils/common";
import type {
  ConfigProviderRow,
  RouterProviderDialogType,
} from "@/views/home/type";

interface RouterProviderFormModel {
  name: string;
  type: string | undefined;
  model: string | undefined;
  enabled: boolean;
  metadataText: string;
  settingsText: string;
}

const props = withDefaults(
  defineProps<{
    dialogData?: ConfigProviderRow;
    dialogType: RouterProviderDialogType;
  }>(),
  {
    dialogData: () => ({}),
  },
);

const emit = defineEmits<{
  close: [];
  saved: [];
}>();

const { t } = useI18n();
const validPattern = /^[a-zA-Z0-9_]+$/;
const formRef = ref<{ validate: () => Promise<void> }>();
const submitting = ref(false);
const formModel = reactive<RouterProviderFormModel>({
  name: "",
  type: undefined,
  model: undefined,
  enabled: false,
  metadataText: "",
  settingsText: "",
});

const isEdit = computed(() => props.dialogType === "edit");
const dialogTitle = computed(() =>
  isEdit.value
    ? t("router.routerProviderEditTitle")
    : t("router.routerProviderCreateTitle"),
);

const validateJson = (_rule: unknown, value: string) => {
  try {
    parseJsonText(value || "", {});
    return Promise.resolve();
  } catch {
    return Promise.reject(t("router.routerProviderJsonRule"));
  }
};

const rules: FormRules = reactive({
  name: [
    {
      required: true,
      message: t("router.routerProviderNameRequired"),
      trigger: "blur",
    },
    {
      pattern: validPattern,
      message: t("router.routerProviderNamePattern"),
      trigger: "blur",
    },
  ],
  type: [
    {
      required: true,
      message: t("router.routerProviderTypeRequired"),
      trigger: "change",
    },
    {
      pattern: validPattern,
      message: t("router.routerProviderNamePattern"),
      trigger: "blur",
    },
  ],
  model: [
    {
      required: true,
      message: t("router.routerProviderModelRequired"),
      trigger: "change",
    },
    {
      pattern: validPattern,
      message: t("router.routerProviderNamePattern"),
      trigger: "blur",
    },
  ],
  enabled: [
    {
      required: true,
      trigger: "change",
    },
  ],
  metadataText: [{ validator: validateJson, trigger: "blur" }],
  settingsText: [{ validator: validateJson, trigger: "blur" }],
});

const syncFormModel = () => {
  const {
    name,
    type,
    model,
    enabled = false,
    metadata,
    settings,
  } = props.dialogData || {};

  formModel.name = typeof name === "string" ? name : "";
  formModel.type = typeof type === "string" ? type : undefined;
  formModel.model = typeof model === "string" ? model : undefined;
  formModel.enabled = Boolean(enabled);
  formModel.metadataText = formatJsonText(metadata, { fallback: "" });
  formModel.settingsText = formatJsonText(settings, { fallback: "" });
};

const formatFormParam = () => {
  const { metadataText = "", settingsText = "", ...formData } = formModel;

  return {
    ...formData,
    metadata: parseJsonText(metadataText, {}),
    settings: parseJsonText(settingsText, {}),
  };
};

const handleSubmit = async () => {
  try {
    await formRef.value?.validate();
    const { name } = formatFormParam();

    submitting.value = true;
    updateRouterProvider(name, formatFormParam())
      .then(() => {
        emit("saved");
      })
      .catch((error) => {
        console.log(error);
      })
      .finally(() => {
        submitting.value = false;
      });
  } catch (error) {
    if (!(error as { errorFields?: unknown[] })?.errorFields) {
      console.log(error);
    }
  }
};

watch(() => props.dialogData, syncFormModel, { immediate: true, deep: true });
</script>

<style scoped lang="less">
.router-provider-form-scroll {
  // max-height: min(72vh, 680px);
  padding-right: 6px;
  overflow-y: auto;
}
</style>
