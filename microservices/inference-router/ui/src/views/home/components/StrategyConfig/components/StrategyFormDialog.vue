<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

<template>
  <a-modal
    :open="true"
    :title="dialogTitle"
    :confirm-loading="submitting"
    centered
    destroyOnClose
    :keyboard="false"
    :maskClosable="false"
    :ok-text="t('common.save')"
    :cancel-text="t('common.cancel')"
    width="720px"
    class="router-strategy-form-dialog"
    @ok="handleSubmit"
    @cancel="emit('close')"
  >
    <div class="router-strategy-form-scroll">
      <a-form
        ref="formRef"
        :model="formModel"
        :rules="rules"
        layout="vertical"
        class="router-strategy-form"
      >
        <a-form-item :label="t('router.routerStrategyName')" name="name">
          <a-input
            v-model:value="formModel.name"
            :disabled="isEdit"
            :placeholder="t('router.routerStrategyNamePlaceholder')"
          />
        </a-form-item>
        <a-form-item
          :label="t('router.routerStrategyDescription')"
          name="description"
        >
          <a-input
            v-model:value="formModel.description"
            :placeholder="t('router.routerStrategyDescriptionPlaceholder')"
          />
        </a-form-item>
        <a-form-item
          :label="t('router.routerStrategyProviderSelector')"
          name="providerSelectorText"
        >
          <a-textarea
            v-model:value="formModel.providerSelectorText"
            :rows="4"
            :placeholder="t('router.routerStrategyProviderSelectorPlaceholder')"
          />
        </a-form-item>
        <a-form-item
          :label="t('router.routerStrategyRequireHealthy')"
          name="requireHealthy"
        >
          <a-radio-group
            v-model:value="formModel.requireHealthy"
            button-style="solid"
          >
            <a-radio :value="true">{{ t("common.yes") }}</a-radio>
            <a-radio :value="false">{{ t("common.no") }}</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item :label="t('router.routerStrategyLimit')" name="limit">
          <a-input-number
            v-model:value="formModel.limit"
            :min="1"
            :precision="0"
            :placeholder="t('router.routerStrategyLimitPlaceholder')"
            style="width: 100%"
          />
        </a-form-item>

        <a-form-item :label="t('router.routerStrategyRules')" name="rulesText">
          <a-textarea
            v-model:value="formModel.rulesText"
            :rows="4"
            :placeholder="t('router.routerStrategyRulesPlaceholder')"
          />
        </a-form-item>
        <a-form-item :label="t('router.routerStrategySort')" name="sortText">
          <a-textarea
            v-model:value="formModel.sortText"
            :rows="4"
            :placeholder="t('router.routerStrategySortPlaceholder')"
          />
        </a-form-item>
      </a-form>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { updateRouterStrategy } from "@/api/router";
import { formatJsonText, parseJsonText } from "@/utils/common";
import type {
  StrategyConfigDialogType,
  StrategyConfigPayload,
  StrategyConfigRow,
} from "@/views/home/type";

interface StrategyConfigFormModel {
  name: string;
  description: string;
  rulesText: string;
  providerSelectorText: string;
  sortText: string;
  requireHealthy: boolean;
  limit: number | null;
}

const props = withDefaults(
  defineProps<{
    dialogData?: StrategyConfigRow;
    dialogType: StrategyConfigDialogType;
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
const validPattern = /^[a-zA-Z0-9._-]+$/;
const formRef = ref<{ validate: () => Promise<void> }>();
const submitting = ref(false);
const formModel = reactive<StrategyConfigFormModel>({
  name: "",
  description: "",
  rulesText: "",
  providerSelectorText: "",
  sortText: "",
  requireHealthy: false,
  limit: null,
});

const isEdit = computed(() => props.dialogType === "edit");
const dialogTitle = computed(() =>
  isEdit.value
    ? t("router.routerStrategyEditTitle")
    : t("router.routerStrategyCreateTitle"),
);

const validateJsonArray = (_rule: unknown, value: string) => {
  try {
    const parsedValue = parseJsonText(value || "", []);
    return Array.isArray(parsedValue)
      ? Promise.resolve()
      : Promise.reject(t("router.routerStrategyJsonArrayRule"));
  } catch {
    return Promise.reject(t("router.routerStrategyJsonRule"));
  }
};

const validateProviderSelector = (_rule: unknown, value: string) => {
  try {
    const parsedValue = parseJsonText(value || "", {});
    const isRecord =
      parsedValue &&
      typeof parsedValue === "object" &&
      !Array.isArray(parsedValue);
    return isRecord
      ? Promise.resolve()
      : Promise.reject(t("router.routerStrategyProviderSelectorRule"));
  } catch {
    return Promise.reject(t("router.routerStrategyJsonRule"));
  }
};

const rules: FormRules = reactive({
  name: [
    {
      required: true,
      message: t("router.routerStrategyNameRequired"),
      trigger: "blur",
    },
    {
      pattern: validPattern,
      message: t("router.routerStrategyNamePattern"),
      trigger: "blur",
    },
  ],
  providerSelectorText: [
    {
      required: true,
      message: t("router.routerStrategyProviderSelectorRequired"),
      trigger: "blur",
    },
    { validator: validateProviderSelector, trigger: "blur" },
  ],
  rulesText: [{ validator: validateJsonArray, trigger: "blur" }],
  sortText: [{ validator: validateJsonArray, trigger: "blur" }],
});

const syncFormModel = () => {
  const strategy = props.dialogData || {};
  formModel.name = typeof strategy.name === "string" ? strategy.name : "";
  formModel.description =
    typeof strategy.description === "string" ? strategy.description : "";
  formModel.rulesText = formatJsonText(strategy.rules, { fallback: "" });
  formModel.providerSelectorText = formatJsonText(strategy.provider_selector, {
    fallback: "",
  });
  formModel.sortText = formatJsonText(strategy.sort, { fallback: "" });
  formModel.requireHealthy = Boolean(strategy.require_healthy);
  formModel.limit =
    typeof strategy.limit === "number" && Number.isFinite(strategy.limit)
      ? strategy.limit
      : null;
};

const formatFormParam = (): StrategyConfigPayload => {
  return {
    description: formModel.description,
    rules: parseJsonText(formModel.rulesText, []) as unknown[],
    provider_selector: parseJsonText(formModel.providerSelectorText, {}),
    sort: parseJsonText(formModel.sortText, []) as unknown[],
    require_healthy: formModel.requireHealthy,
    limit: formModel.limit,
  };
};

const handleSubmit = async () => {
  try {
    await formRef.value?.validate();
    const { name } = formModel;

    submitting.value = true;
    updateRouterStrategy(name, formatFormParam())
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
.router-strategy-form-scroll {
  max-height: min(72vh, 680px);
  padding-right: 6px;
  overflow-y: auto;
}
</style>
