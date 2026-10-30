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
    width="640px"
    class="router-provider-form-dialog"
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
            <a-radio :value="true">
              {{ t("common.yes") }}
            </a-radio>
            <a-radio :value="false">
              {{ t("common.no") }}
            </a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item
          :label="t('router.routerProviderFallback')"
          name="fallback"
        >
          <a-radio-group
            v-model:value="formModel.fallback"
            button-style="solid"
          >
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
    <template #footer>
      <div class="footer-wrap">
        <a-button type="primary" ghost @click="handleCancel">
          {{ t("common.cancel") }}
        </a-button>
        <a-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ t("common.update") }}
        </a-button>
      </div>
    </template>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { updateRouterProvider } from "@/api/providerConfig";
import { formatJsonText, parseJsonText } from "@/utils/common";
import type {
  ConfigProviderRow,
  RouterProviderDialogType,
} from "@/types/router";

interface RouterProviderFormModel {
  name: string;
  type: string;
  model: string;
  enabled: boolean;
  fallback: boolean;
  metadataText: string;
  settingsText: string;
}

const props = withDefaults(
  defineProps<{
    dialogData?: ConfigProviderRow;
    dialogType: RouterProviderDialogType;
  }>(),
  {
    dialogData: () => ({ name: "" }),
  },
);

const emit = defineEmits<{
  close: [];
  saved: [];
}>();

const handleCancel = () => emit("close");

const { t } = useI18n();
const validPattern = /^[a-zA-Z0-9_]+$/;
const formRef = ref<{ validate: () => Promise<void> }>();
const submitting = ref(false);
const formModel = reactive<RouterProviderFormModel>({
  name: "",
  type: "",
  model: "",
  enabled: false,
  fallback: false,
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
    const parsed = parseJsonText<unknown>(value || "", {});
    if (
      parsed !== null &&
      typeof parsed === "object" &&
      !Array.isArray(parsed)
    ) {
      return Promise.resolve();
    }
  } catch {
    return Promise.reject(t("router.routerProviderJsonRule"));
  }
  return Promise.reject(t("router.routerProviderJsonRule"));
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
  ],
  enabled: [
    {
      required: true,
      trigger: "change",
    },
  ],
  fallback: [
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
    type = "",
    model = "",
    enabled = false,
    fallback = false,
    metadata,
    settings,
  } = props.dialogData;

  formModel.name = name;
  formModel.type = type;
  formModel.model = model;
  formModel.enabled = enabled;
  formModel.fallback = fallback;
  formModel.metadataText = formatJsonText(metadata, { fallback: "" });
  formModel.settingsText = formatJsonText(settings, { fallback: "" });
};

const formatFormParam = () => {
  const { metadataText, settingsText, ...formData } = formModel;

  return {
    ...formData,
    metadata: parseJsonText(metadataText, {}),
    settings: parseJsonText(settingsText, {}),
  };
};

const handleSubmit = async () => {
  try {
    await formRef.value?.validate();
    const payload = formatFormParam();

    submitting.value = true;
    updateRouterProvider(formModel.name, payload)
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
.footer-wrap {
  display: flex;
  justify-content: space-between;
}

.router-provider-form-scroll {
  // max-height: min(72vh, 680px);
  padding-right: 6px;
  overflow-y: auto;
}
</style>
